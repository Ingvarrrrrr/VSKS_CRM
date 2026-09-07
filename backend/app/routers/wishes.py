from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, delete, func, or_, and_
from datetime import date, datetime
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.auth.jwt import (
    get_current_user, get_org_filter,
    MANAGER_ROLES, OWNER_ROLES,
)
from app.auth.visibility import build_visibility_clause, get_visible_user_ids, get_visible_subsidy_ids
from app.models.user import User
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.wish_member import WishMember
from app.schemas.wishes import WishCreate, WishUpdate, WishOut, WishItemPatch, WishItemPurchaseMatch, WishPurchaseSummary
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.feo_category import FeoCategory
from app.services.text_match import normalize as _normalize_name
from app.services.feo_plan import assert_tz_not_over_plan
from app.services.item_contractor import item_contractor as _item_contractor, set_item_contractor
# _move_or_detach_planned_item/_deactivate_if_orphaned нужны только update_wish
# (ниже) — остальные хелперы автозаведения плана (_auto_assign_planned_items/
# _backfill_item_type_from_plan) переехали в app/services/wish_distribution.py
# вместе с _distribute_wish_to_purchases/_sync_purchase_from_wish, которые их
# используют (Правило №5, сессия 2026-09-06).
from app.services.plan_autoassign import (
    move_or_detach_planned_item as _move_or_detach_planned_item,
    deactivate_if_orphaned as _deactivate_if_orphaned,
)
from decimal import Decimal
from app.services.wish_tabs import WISH_TAB_STATUS_SETS, wish_tab_statuses
# Перенос заявки в План закупок и обратно (Правило №5, сессия 2026-09-06,
# разрезание wishes.py по образцу purchases.py → purchase_ops.py) — вынесены в
# app/services/wish_distribution.py. Импорт здесь ОБЯЗАТЕЛЕН для re-export:
# app/routers/wish_approvals.py и app/services/wish_advance_conversion.py делают
# `from app.routers.wishes import _withdraw_wish_from_plan/_reset_approvals/
# _distribute_wish_to_purchases` — эти имена обязаны остаться доступны как
# атрибуты этого модуля. _collect_excess_warnings/_sync_purchase_from_wish нужны
# по тому же принципу — app/routers/wish_convert.py вызывает их через
# `wishes_core.<имя>` (см. докстринг wish_transitions.py про monkeypatch), а не
# прямым импортом из wish_distribution, чтобы весь путь «правки ядра видны
# роутерам-переходам» шёл одним способом.
from app.services.wish_distribution import (
    _withdraw_wish_from_plan,
    _reset_approvals,
    _distribute_wish_to_purchases,
    _collect_excess_warnings,
    _sync_purchase_from_wish,
)


def _is_saas(user: User) -> bool:
    """SaaS-роли (superadmin/account_owner) — обходят любые status-guard'ы."""
    return user.role in OWNER_ROLES


router = APIRouter(prefix="/api/wishes", tags=["wishes"])

# Phase 31: fields tracked for diff-highlighting (D-05..D-09)
# estimated_price is the wish amount proxy (Wish has no total_price column)
WISH_TRACKED_FIELDS: set[str] = {
    "title", "description", "status", "subsidy_id", "estimated_price",
}


def _enrich(w: Wish) -> WishOut:
    """Convert Wish ORM object to WishOut, filling computed name fields."""
    d = WishOut.model_validate(w)
    if w.creator:
        d.creator_name = w.creator.full_name or w.creator.username
    if w.approver:
        d.approver_name = w.approver.full_name or w.approver.username
    if w.subsidy:
        d.subsidy_name = w.subsidy.name
    if w.assignee:
        d.assignee_name = w.assignee.full_name or w.assignee.username
        d.assigned_to_name = d.assignee_name  # alias for legacy frontend
    if getattr(w, 'event', None):
        d.event_name = w.event.name
    if getattr(w, 'executor', None):
        d.executor_name = w.executor.full_name or w.executor.username
    if getattr(w, 'stopped_by_user', None):
        d.stopped_by_name = w.stopped_by_user.full_name or w.stopped_by_user.username
    if getattr(w, 'rejected_by_user', None):
        d.rejected_by_name = w.rejected_by_user.full_name or w.rejected_by_user.username
    # Контрагент — ПРАВИЛО №6 (группа D5): единственный читатель —
    # item_contractor.item_contractor (FK, когда задан, иначе свободный текст).
    # w.contractor — relationship lazy="selectin" (см. models/wish.py), уже
    # подгружена без доп. запроса.
    _wc = _item_contractor(w, contractor=getattr(w, 'contractor', None))
    if _wc["contractor_name"]:
        d.contractor_display_name = _wc["contractor_name"]
    return d


async def _load_wish(wish_id: int, db: AsyncSession) -> Wish:
    """Load wish with all relationships."""
    result = await db.execute(
        select(Wish)
        .options(
            selectinload(Wish.creator),
            selectinload(Wish.approver),
            selectinload(Wish.assignee),
            selectinload(Wish.subsidy),
            selectinload(Wish.event),
            selectinload(Wish.executor),
            selectinload(Wish.items),
            selectinload(Wish.stopped_by_user),
            selectinload(Wish.contractor),
            selectinload(Wish.rejected_by_user),
        )
        .where(Wish.id == wish_id)
    )
    wish = result.scalar_one_or_none()
    if wish is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return wish


async def _attach_purchase_matches(wish: Wish, enriched: WishOut, db: AsyncSession) -> None:
    """W-diff (2026-08-13, карточка заявки только): для каждой позиции заявки
    находит её «двойника» в закупке(ах), созданных из этой заявки, и заполняет
    WishItemOut.purchase_match (см. WishItemPurchaseMatch за назначением полей).

    Сопоставление (владелец, 2026-08-13, доразбор неоднозначности заявки №31 —
    «Перчатки … размер L» дважды в заявке, 4 шт/«Финал» и 20 шт/«Окружные»,
    человек различает их количеством):
      1. По PurchaseItem.wish_item_id — надёжная прямая связь.
      2. Иначе — по точному нормализованному имени (app.services.text_match.normalize)
         среди позиций закупок ЭТОЙ ЖЕ заявки, у которых wish_item_id ПУСТ (позиции
         с прямой связью уже разобраны шагом 1 и не участвуют в поиске по имени —
         иначе можно «увести» чужого двойника). Если под этим именем ИЗНАЧАЛЬНО
         (до любых claim'ов) был ровно один кандидат — match_method='item_name'.
      3. Если изначально кандидатов было НЕСКОЛЬКО — сужаем точным совпадением
         quantity. Единственный кандидат с подходящим количеством —
         match_method='item_name_qty' (связь по имени И количеству, честно
         отличается от простого 'item_name'). Это касается КАЖДОЙ позиции
         заявки из такой группы, даже если к моменту её обработки в пуле
         остался только один кандидат (соседняя позиция уже забрала другой) —
         статус группы «была неоднозначна по имени» фиксируется ДО обработки,
         чтобы обе позиции пары «4 шт/20 шт» получили одинаково честную метку,
         а не «первая — по количеству, вторая — как бы просто по имени».
      4. Всё ещё больше одного кандидата с подходящим количеством (или у позиции
         заявки количество не задано) — неоднозначность, наугад не выбираем:
         match_method='item_name_ambiguous' + ambiguous_candidates_count.
         Остальные поля пустые.
      5. Не нашлось вовсе — все поля None.

    Каждый кандидат-двойник закупки достаётся НЕ БОЛЕЕ ЧЕМ одной позиции заявки:
    выбранный кандидат удаляется из пула конкретного имени (list.pop/remove),
    иначе при повторе того же имени в заявке (см. пример выше) вторая позиция
    получила бы того же самого «уже занятого» двойника.

    Один пакетный запрос закупок + один пакетный запрос их позиций (с JOIN на
    feo_categories.name) на всю заявку — без N+1 по позициям.
    """
    purchases_rows = (await db.execute(
        select(Purchase.id, Purchase.purchase_number, Purchase.status, Purchase.stopped_at)
        .where(Purchase.wish_id == wish.id)
    )).all()
    purchase_info = {r[0]: r for r in purchases_rows}  # purchase_id -> (id, number, status, stopped_at)
    purchase_ids = list(purchase_info.keys())

    purchase_items_rows = []
    if purchase_ids:
        purchase_items_rows = (await db.execute(
            select(PurchaseItem, FeoCategory.name)
            .outerjoin(FeoCategory, FeoCategory.id == PurchaseItem.feo_category_id)
            .where(PurchaseItem.purchase_id.in_(purchase_ids))
        )).all()

    direct_by_wish_item_id: dict[int, tuple] = {}
    unclaimed_by_name: dict[str, list[tuple]] = {}
    for pi, feo_name in purchase_items_rows:
        if pi.wish_item_id is not None:
            direct_by_wish_item_id.setdefault(pi.wish_item_id, (pi, feo_name))
        else:
            key = _normalize_name(pi.item_name or "")
            if key:
                unclaimed_by_name.setdefault(key, []).append((pi, feo_name))
    # Кол-во кандидатов под каждое имя ДО начала claim'а (снимок) — нужно, чтобы
    # оба «близнеца» одной пары «одинаковое имя, разное количество» (см. докстринг)
    # были помечены одинаково 'item_name_qty', а не «первый по количеству, второй
    # по остатку» (иначе один и тот же по сути разбор количества выглядел бы для
    # фронта как связь по имени БЕЗ количества у второй позиции).
    original_candidate_count: dict[str, int] = {k: len(v) for k, v in unclaimed_by_name.items()}

    def _build_match(method: str, pi, feo_name) -> WishItemPurchaseMatch:
        p_row = purchase_info.get(pi.purchase_id)
        return WishItemPurchaseMatch(
            match_method=method,
            purchase_item_id=pi.id,
            purchase_id=pi.purchase_id,
            purchase_number=p_row[1] if p_row else None,
            purchase_status=p_row[2] if p_row else None,
            purchase_stopped_at=p_row[3] if p_row else None,
            feo_category_id=pi.feo_category_id,
            feo_category_name=feo_name,
            quantity=float(pi.quantity) if pi.quantity is not None else None,
            unit_price=float(pi.unit_price) if pi.unit_price is not None else None,
            total_price=float(pi.total_price) if pi.total_price is not None else None,
        )

    wish_items = list(wish.items or [])
    for w_item, out_item in zip(wish_items, enriched.items):
        direct = direct_by_wish_item_id.get(w_item.id)
        if direct is not None:
            out_item.purchase_match = _build_match("wish_item_id", direct[0], direct[1])
            continue
        key = _normalize_name(w_item.item_name or "")
        candidates = unclaimed_by_name.get(key, []) if key else []
        was_ambiguous_name = original_candidate_count.get(key, 0) > 1
        if not candidates:
            continue  # не нашлось — purchase_match остаётся None (default)
        if len(candidates) == 1 and not was_ambiguous_name:
            # Имя изначально указывало ровно на одну позицию закупки — количество
            # не потребовалось.
            pi, feo_name = candidates.pop(0)
            out_item.purchase_match = _build_match("item_name", pi, feo_name)
        else:
            # Имя само по себе неоднозначно (сейчас или изначально — включая
            # случай, когда «сосед» по имени уже разобран выше и остался ровно
            # один кандидат: для НЕГО это тоже разбор по количеству, а не по
            # голому имени). Сужаем точным совпадением quantity.
            qty_matches = [
                c for c in candidates
                if w_item.quantity is not None and c[0].quantity == w_item.quantity
            ]
            if len(qty_matches) == 1:
                pi, feo_name = qty_matches[0]
                candidates.remove((pi, feo_name))  # claim — не достанется другой позиции заявки
                out_item.purchase_match = _build_match("item_name_qty", pi, feo_name)
            else:
                out_item.purchase_match = WishItemPurchaseMatch(
                    match_method="item_name_ambiguous",
                    ambiguous_candidates_count=len(candidates),
                )


async def _is_wish_member(wish_id: int, user_id: int, db: AsyncSession) -> bool:
    res = await db.execute(
        select(WishMember.id).where(
            WishMember.wish_id == wish_id,
            WishMember.user_id == user_id,
        ).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def _ensure_no_pending_approvals(
    wish, db: AsyncSession, current_user=None, allow_override: bool = False
) -> None:
    """Конвертация заявки запрещена, пока цепочка согласования не завершена:
    иначе заявка уходит в converted, а pending-согласующие «зависают»
    и не видят её во вкладке «На согласовании мне».

    Собственное pending-согласование текущего пользователя блоком не считается:
    «Быстрое одобрение» согласующим = его решение approved. Оно фиксируется в цепочке,
    и блокировка снимается, если других pending-согласующих не осталось.

    allow_override=True + менеджер/SaaS → одобряет ВСЕ pending от имени current_user,
    не блокирует конвертацию."""
    from datetime import datetime, timezone
    from app.models.wish_approval import WishApproval
    pending = (await db.execute(
        select(WishApproval)
        .where(WishApproval.wish_id == wish.id, WishApproval.status == "pending")
        .order_by(WishApproval.order_num)
    )).scalars().all()

    own = [a for a in pending if current_user is not None and a.user_id == current_user.id]
    others = [a for a in pending if not (current_user is not None and a.user_id == current_user.id)]

    if others:
        # W3: менеджер/SaaS может одобрить чужие pending без блокировки
        is_manager = (
            current_user is not None
            and (
                _is_saas(current_user)
                or getattr(current_user, 'role', None) in MANAGER_ROLES
            )
        )
        if allow_override and is_manager:
            override_comment = (
                f"Одобрено без согласования остальных "
                f"({getattr(current_user, 'full_name', None) or getattr(current_user, 'username', '')})"
            )
            now = datetime.now(timezone.utc)
            for a in others:
                a.status = "approved"
                a.decided_at = now
                a.decided_by_user_id = current_user.id
                a.decided_by_username = current_user.full_name or current_user.username
                a.comment = override_comment
            await db.flush()
        else:
            names = ", ".join(a.approver_full_name or f"пользователь #{a.user_id}" for a in others)
            raise HTTPException(
                status_code=409,
                detail=f"У заявки незавершённое согласование ({names}). "
                       "Дождитесь решения согласующих или удалите цепочку согласования.",
            )

    # Других pending нет (или они одобрены выше) — фиксируем собственное решение согласующего как approved
    for a in own:
        a.status = "approved"
        a.decided_at = datetime.now(timezone.utc)
        a.decided_by_user_id = current_user.id
        a.decided_by_username = current_user.full_name or current_user.username
    if own:
        await db.flush()


def _as_date(value):
    """needed_date приходит из нетипизированного items: list — Pydantic его не приводит."""
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        return date.fromisoformat(value[:10])
    if isinstance(value, datetime):
        return value.date()
    return value


def _eff_date(wish, item):
    """Эффективная плановая дата позиции: приоритет
    позиция(needed_date) → Срок исполнения(execution_deadline) → Желаемая дата(desired_date)."""
    return (
        getattr(item, "needed_date", None)
        or getattr(wish, "execution_deadline", None)
        or getattr(wish, "desired_date", None)
    )


async def _ensure_needed_dates(wish, db, items, context: str = "convert") -> None:
    """W2-гейт: если субсидия требует плановые даты — проверяем все items.
    Бросает HTTPException 409 с error_code='missing_needed_dates' если есть позиции без даты.
    Авансовые отчёты пропускаются вызывающим — этот хелпер не проверяет source.
    context='submit' — сообщение для отправки на согласование; 'convert' (default) — для переноса в план закупок."""
    if not wish.subsidy_id:
        return
    from app.models.subsidy import Subsidy
    subsidy = await db.get(Subsidy, wish.subsidy_id)
    if not (subsidy and subsidy.require_planned_dates):
        return
    items_without_date = [it for it in items if not _eff_date(wish, it)]
    if not items_without_date:
        return
    names_list = ", ".join(f'«{it.item_name}»' for it in items_without_date[:5])
    suffix = f" и ещё {len(items_without_date) - 5} поз." if len(items_without_date) > 5 else ""
    if context == "submit":
        intro = (
            f"Невозможно отправить заявку на согласование: у следующих позиций не указана "
            f"дата потребности (к какой дате планируется закупить): {names_list}{suffix}."
        )
    else:
        intro = (
            f"Невозможно перенести заявку в План закупок: у следующих позиций не указана "
            f"дата потребности (к какой дате планируется закупить): {names_list}{suffix}."
        )
    message = (
        f"{intro} "
        f"Без даты потребности ФЭО не может распределить расходы по месяцам. "
        f"Укажите дату потребности для позиции, либо «Срок исполнения», либо «Желаемую дату поставки/исполнения» "
        f"в заявке. Требование дат можно отключить в настройках субсидии "
        f"(доступно Хозяину аккаунта)."
    )
    raise HTTPException(
        status_code=409,
        detail={
            "message": message,
            "error_code": "missing_needed_dates",
            "missing_item_ids": [it.id for it in items_without_date],
            "missing_item_names": [it.item_name for it in items_without_date],
        },
    )


async def _ensure_feo_categories_assigned(wish, items, db: AsyncSession) -> None:
    """Жёсткий гейт «без категории ФЭО закупка не проходит» (владелец, 2026-08-11).

    Реальный случай с прода: заявка №32 «Приобретение Пикапов» была согласована,
    из неё создалась закупка РЕЕ-2026-00889 (Great Wall POER, 2 шт × 4 000 000), но
    у позиции и у самой заявки feo_category_id был пуст. Автозаведение плановой
    позиции (_auto_assign_planned_items) берёт эффективную категорию, не находит её
    и молча пропускает позицию — закупка осталась сиротой, её сумма не попала ни в
    один план ФЭО.

    Проверяем ДО любых мутаций (при отказе ни одна закупка не создаётся частично):
    у КАЖДОЙ позиции должна быть эффективная категория — item.feo_category_id, а
    если он не задан — фолбэк на wish.feo_category_id. Категория должна не только
    быть задана, но и реально существовать в справочнике (FeoCategory) — ссылка на
    удалённую категорию (структуру ФЭО субсидии пересоздавали) раньше молча
    обнулялась и закупка создавалась без ФЭО (см. историю ветки convert_warning,
    убрана этим гейтом) — именно так обнулилась категория у заявки №32 ещё до
    автозаведения. Теперь это тоже отказ, а не предупреждение постфактум.

    wish.feo_category_id, если задан, тоже обязан существовать — он пишется в
    Purchase.feo_category_id напрямую (не только как фолбэк для позиций без своей
    категории), битая ссылка уронила бы INSERT закупки FK-violation'ом (500 без
    объяснения), если бы её не отловили здесь заранее.

    `items` — WishItem ORM или dict payload (см. _item_field) — вызывающий обязан
    заранее отфильтровать строки-заготовки (_is_meaningful_item), иначе пустая
    заготовка без названия тоже потребует категорию.
    """
    from app.models.feo_category import FeoCategory

    wish_cat_id = wish.feo_category_id
    ref_ids = {i for i in ({wish_cat_id} | {_item_field(it, 'feo_category_id') for it in items}) if i}
    valid_ids: set[int] = set()
    if ref_ids:
        valid_ids = set((await db.execute(
            select(FeoCategory.id).where(FeoCategory.id.in_(ref_ids))
        )).scalars().all())

    wish_cat_ok = wish_cat_id is None or wish_cat_id in valid_ids
    problem_names: list[str] = []
    for it in items:
        item_cat = _item_field(it, 'feo_category_id')
        eff_cat = item_cat or wish_cat_id
        if eff_cat is None or eff_cat not in valid_ids:
            problem_names.append(str(_item_field(it, 'item_name') or 'без названия'))

    if not problem_names and wish_cat_ok:
        return

    names_list = ", ".join(f'«{n}»' for n in problem_names[:10])
    suffix = f" и ещё {len(problem_names) - 10} поз." if len(problem_names) > 10 else ""
    parts: list[str] = []
    if problem_names:
        parts.append(
            f"у следующих позиций нет категории ФЭО, либо она ссылается на удалённую "
            f"из справочника категорию: {names_list}{suffix}"
        )
    if not wish_cat_ok:
        parts.append(
            "категория ФЭО самой заявки была удалена из справочника "
            "(структуру ФЭО субсидии пересоздавали)"
        )
    message = (
        "Невозможно перенести заявку в План закупок: " + "; ".join(parts) + ". "
        "Выберите категорию ФЭО для каждой позиции (или для заявки целиком в разделе "
        "«Категория ФЭО»), а если категория неизвестна — выберите «Не определена». "
        "Без категории закупка не попадёт ни в один план ФЭО и её сумма потеряется."
    )
    raise HTTPException(
        status_code=409,
        detail={
            "message": message,
            "error_code": "missing_feo_category",
            "missing_item_names": problem_names,
        },
    )


# W1: статусы «дошли до договора» — блокируют редактирование привязанной заявки
CONTRACTED_STATUSES = ("contracted", "ordered", "delivered", "paid")


async def _wish_linked_purchases(wish_id: int, db: AsyncSession) -> list:
    """Возвращает список закупок, привязанных к заявке."""
    res = await db.execute(select(Purchase).where(Purchase.wish_id == wish_id))
    return res.scalars().all()


async def _wish_purchase_summaries_map(wish_ids: list, db: AsyncSession) -> dict:
    """Пункт 4 (владелец, 2026-08-13): «из согласованной заявки — переход в её
    закупки; если их несколько — выпадающий список с номером/статусом/суммой».
    purchase_ids (List[int], см. рядом) отдаёт только id — этого мало для
    осмысленного меню. Формат карточки закупки вынесен в
    app.services.purchase_summary.purchase_summaries_by_id (план
    zany-fluttering-mountain.md, 2026-08-13) — переиспользуется и «виновниками»
    превышения плана (excess_plan_items, см. app.services.feo_plan), чтобы
    формат карточки не разъехался на два.
    """
    out: dict = {}
    if not wish_ids:
        return out
    from app.services.purchase_summary import purchase_summaries_by_id

    link_rows = (await db.execute(
        select(Purchase.wish_id, Purchase.id)
        .where(Purchase.wish_id.in_(wish_ids))
        .order_by(Purchase.id)
    )).all()
    if not link_rows:
        return out
    summaries = await purchase_summaries_by_id(db, (pid for _wid, pid in link_rows))
    for wid, pid in link_rows:
        s = summaries.get(pid)
        if s is None:
            continue
        out.setdefault(wid, []).append(WishPurchaseSummary(**s))
    return out


def _item_field(it, name: str, default=None):
    """Универсальный доступ к полю позиции: и pydantic/dict-payload (body.items —
    список dict), и ORM WishItem (атрибуты) должны обрабатываться одним предикатом."""
    if isinstance(it, dict):
        return it.get(name, default)
    return getattr(it, name, default)


def _is_meaningful_item(it) -> bool:
    """Строка-заготовка (без названия, количества и суммы) — фронт создаёт их
    заранее для будущего ввода; в БД, План закупок и в гейты они попадать не должны.
    Принимает как ORM WishItem, так и «сырой» dict из body.items."""
    name = _item_field(it, "item_name") or ""
    quantity = _item_field(it, "quantity") or 0
    total_price = _item_field(it, "total_price") or 0
    return bool(str(name).strip() or float(quantity or 0) or float(total_price or 0))


async def _wish_locked_descr(wish_id: int, db: AsyncSession) -> Optional[str]:
    """Человекочитаемое описание закупок, из-за которых заявка заблокирована
    для правки (Договор+) — None, если блокирующих закупок нет.

    Владелец увидел на проде сообщение «на этапе «Договор»» для закупки в
    статусе `ordered` («Заказано») — CONTRACTED_STATUSES шире одного статуса
    «Договор» (contracted/ordered/delivered/paid), а текст называл только его.
    Единый хелпер вместо копипасты формата в двух местах (409 при PUT и при
    удалении позиций) — чтобы формулировка не расходилась. Формат каждой
    закупки: `№{purchase_number or id} «{item_name}» — стадия «{label}»`.
    """
    from app.routers.purchase_export import _STATUS_LABELS
    purchases = await _wish_linked_purchases(wish_id, db)
    locked = [p for p in purchases if p.status in CONTRACTED_STATUSES]
    if not locked:
        return None
    return "; ".join(
        f"№{p.purchase_number or p.id} «{p.item_name or ''}» — стадия «{_STATUS_LABELS.get(p.status, p.status)}»"
        for p in locked
    )


async def _notify_pending_approvers(wish, db: AsyncSession, requester_name: str) -> None:
    """Уведомляет согласующих из цепочки о необходимости решения.

    sequential → уведомить первого pending; parallel → уведомить всех.
    Повторно используется из submit_wish и update_wish (при повторном согласовании).
    """
    try:
        from app.models.wish_approval import WishApproval
        from app.notifications import notify_wish_approval_step
        from app.models.user import User as _User
        pending = (await db.execute(
            select(WishApproval).where(
                WishApproval.wish_id == wish.id,
                WishApproval.status == "pending",
            ).order_by(WishApproval.order_num)
        )).scalars().all()
        if pending:
            targets = pending[:1] if (wish.approval_mode or "sequential") == "sequential" else pending
            for ap in targets:
                if ap.user_id and ap.user_id != wish.created_by:
                    approver_user = await db.get(_User, ap.user_id)
                    if approver_user:
                        await notify_wish_approval_step(wish, approver_user, requester_name)
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning("notify approvers failed: %s", e)


async def _build_wishes_query(
    q,
    current_user: User,
    db: AsyncSession,
    *,
    mine_only: bool = False,
    assigned_to_me: bool = False,
    subordinates_only: bool = False,
    creator_id: Optional[int] = None,
    assigned_to_id: Optional[int] = None,
    subsidy_id: Optional[int] = None,
    org_id: Optional[int] = None,
    account_org_id: Optional[int] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    deadline_from: Optional[date] = None,
    deadline_to: Optional[date] = None,
):
    """Общая видимость + доп. фильтры для GET /wishes/ и GET /wishes/counts.

    Вынесено из list_wishes (сессия 2026-09-01, жалоба владельца на счётчики
    вкладок), чтобы список и счётчики видели РОВНО одни и те же заявки — иначе
    числа разъедутся между вкладкой и бейджем. НЕ накладывает статус-фильтр,
    order_by, offset/limit — это решает вызывающий (у /counts своя логика
    группировки, у списка — своя пагинация).
    """
    org_ids = get_org_filter(current_user)
    vis = await get_visible_subsidy_ids(current_user, db, "wishes")
    if vis is not None:
        # Two-level gate: rows WITH subsidy → gate by vis; rows WITHOUT subsidy → org gate
        null_branch = (
            and_(Wish.subsidy_id.is_(None), Wish.org_id.in_(org_ids))
            if org_ids is not None
            else Wish.subsidy_id.is_(None)
        )
        q = q.where(or_(Wish.subsidy_id.in_(vis), null_branch))
    elif org_ids is not None:
        # SaaS role but org restriction still applies (e.g. account_owner with org_id set)
        q = q.where(Wish.org_id.in_(org_ids))

    # Preload wish_ids where current user is a participant (for visibility extension)
    member_res = await db.execute(
        select(WishMember.wish_id).where(WishMember.user_id == current_user.id)
    )
    member_wish_ids = {r[0] for r in member_res.all()}

    if assigned_to_me:
        # Explicit shortcut: wishes where I am the designated approver
        # или я — согласующий из цепочки (WishApproval)
        from app.models.wish_approval import WishApproval
        appr_res = await db.execute(
            select(WishApproval.wish_id).where(WishApproval.user_id == current_user.id)
        )
        appr_wish_ids = {r[0] for r in appr_res.all()}
        if appr_wish_ids:
            q = q.where(or_(Wish.assigned_to == current_user.id, Wish.id.in_(appr_wish_ids)))
        else:
            q = q.where(Wish.assigned_to == current_user.id)
    elif mine_only or current_user.role == 'employee':
        # Employee always sees only own + wishes they are a participant in
        base_cond = Wish.created_by == current_user.id
        if member_wish_ids:
            q = q.where(or_(base_cond, Wish.id.in_(member_wish_ids)))
        else:
            q = q.where(base_cond)
    elif subordinates_only:
        # Phase 28: use unified visibility helper (covers SaaS bypass + hierarchy +
        # dept heads + managed orgs + UOA org_admin/manager)
        visible_uids = await get_visible_user_ids(current_user, db)
        if visible_uids is None:
            # SaaS role (superadmin/account_owner) → видят всё
            # (org filter уже применён выше). Дополнительных фильтров не нужно.
            pass
        else:
            # «Заявки сотрудников» = видимые подчинённые + сам пользователь
            # (руководитель — тоже сотрудник, свои заявки видит здесь же)
            sub_ids = set(visible_uids) | {current_user.id}
            q = q.where(Wish.created_by.in_(sub_ids))
    else:
        # Phase 28: unified visibility helper + member visibility
        clause = await build_visibility_clause(current_user, db, 'wish')
        if clause is not None:
            if member_wish_ids:
                q = q.where(or_(clause, Wish.id.in_(member_wish_ids)))
            else:
                q = q.where(clause)

    # Дополнительные фильтры (применяются после visibility — только сужают)
    if creator_id is not None:
        q = q.where(Wish.created_by == creator_id)
    if assigned_to_id is not None:
        q = q.where(Wish.assigned_to == assigned_to_id)
    if subsidy_id is not None:
        q = q.where(Wish.subsidy_id == subsidy_id)
    if org_id is not None:
        q = q.where(Wish.org_id == org_id)
    if account_org_id is not None:
        # Аккаунт = корневая орг + все её дочерние (root_org_id/parent_org_id)
        from app.models.organization import Organization
        acc_orgs = select(Organization.id).where(or_(
            Organization.id == account_org_id,
            Organization.root_org_id == account_org_id,
            Organization.parent_org_id == account_org_id,
        ))
        q = q.where(Wish.org_id.in_(acc_orgs))
    if created_from is not None:
        q = q.where(func.date(Wish.created_at) >= created_from)
    if created_to is not None:
        q = q.where(func.date(Wish.created_at) <= created_to)
    if deadline_from is not None:
        q = q.where(Wish.desired_date >= deadline_from)
    if deadline_to is not None:
        q = q.where(Wish.desired_date <= deadline_to)

    return q


@router.get("/counts")
async def wish_tab_counts(
    mine_only: bool = False,
    assigned_to_me: bool = False,
    subordinates_only: bool = False,
    creator_id: Optional[int] = None,
    assigned_to_id: Optional[int] = None,
    subsidy_id: Optional[int] = None,
    org_id: Optional[int] = None,
    account_org_id: Optional[int] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    deadline_from: Optional[date] = None,
    deadline_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Счётчики по вкладкам «Заявки на закупку» — с теми же параметрами
    видимости, что и GET /wishes/, но COUNT()-ом, а не выборкой записей.

    Жалоба владельца (сессия 2026-09-01): список обрезан limit=50, поэтому
    сравнивать «сколько заявок» по длине ответа списка нельзя в принципе —
    нужен отдельный точный счётчик. Вкладки накопительные (см.
    app/services/wish_tabs.py): «Отправленные» включает approved/rejected/
    converted, «Одобренные» включает converted и т.д. — один GROUP BY по
    точному статусу, накопление сумм в Python (без 6 отдельных COUNT-запросов).
    """
    q = await _build_wishes_query(
        select(Wish.status, func.count(Wish.id)),
        current_user, db,
        mine_only=mine_only, assigned_to_me=assigned_to_me, subordinates_only=subordinates_only,
        creator_id=creator_id, assigned_to_id=assigned_to_id, subsidy_id=subsidy_id,
        org_id=org_id, account_org_id=account_org_id,
        created_from=created_from, created_to=created_to,
        deadline_from=deadline_from, deadline_to=deadline_to,
    )
    q = q.group_by(Wish.status)
    result = await db.execute(q)
    exact_counts: dict[str, int] = {row_status: cnt for row_status, cnt in result.all()}

    return {
        tab: sum(exact_counts.get(s, 0) for s in statuses)
        for tab, statuses in WISH_TAB_STATUS_SETS.items()
    }


@router.get("/", response_model=list[WishOut])
async def list_wishes(
    status: Optional[str] = None,
    mine_only: bool = False,
    assigned_to_me: bool = False,
    subordinates_only: bool = False,
    creator_id: Optional[int] = None,
    assigned_to_id: Optional[int] = None,
    subsidy_id: Optional[int] = None,
    org_id: Optional[int] = None,
    account_org_id: Optional[int] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    deadline_from: Optional[date] = None,
    deadline_to: Optional[date] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List wishes with unified visibility (Phase 28 Bundle 2B).
    assigned_to_me=true: wishes where current user is the assignee.
    subordinates_only=true: wishes created by direct subordinates (not current user).
    mine_only=true / role==employee: show only own wishes (shortcut filters).

    status: имя вкладки ('draft'/'submitted'/'approved'/'rejected'/'converted'/'all')
    фильтрует НАКОПИТЕЛЬНО через wish_tab_statuses (сессия 2026-09-01, жалоба
    владельца) — 'submitted' включает approved/rejected/converted и т.д.
    Отсутствие параметра сохраняет ПРЕЖНЕЕ поведение (список без converted) —
    на него рассчитывают другие потребители эндпоинта (см. wish_tab_statuses
    докстринг и вызовы GET /wishes/ без status в useRiskScores.ts и
    WishesView.vue::loadWishes/loadIncoming).
    """
    q = select(Wish).options(
        selectinload(Wish.creator),
        selectinload(Wish.approver),
        selectinload(Wish.assignee),
        selectinload(Wish.subsidy),
        selectinload(Wish.event),
        selectinload(Wish.executor),
        selectinload(Wish.items),
        selectinload(Wish.stopped_by_user),
        selectinload(Wish.contractor),
        selectinload(Wish.rejected_by_user),
    )
    q = await _build_wishes_query(
        q, current_user, db,
        mine_only=mine_only, assigned_to_me=assigned_to_me, subordinates_only=subordinates_only,
        creator_id=creator_id, assigned_to_id=assigned_to_id, subsidy_id=subsidy_id,
        org_id=org_id, account_org_id=account_org_id,
        created_from=created_from, created_to=created_to,
        deadline_from=deadline_from, deadline_to=deadline_to,
    )

    if status and status != 'all':
        # Накопительная цепочка (владелец, 2026-09-01): именованная вкладка
        # включает всё, что когда-либо прошло через это состояние.
        q = q.where(Wish.status.in_(wish_tab_statuses(status)))
    elif status == 'all':
        # Явное «Все» — действительно всё, включая draft и converted.
        pass
    else:
        # status отсутствует вовсе: ПРЕЖНЕЕ поведение не меняем — по умолчанию
        # «Заявки» = в работе; распределённые (converted) живут в «Закупках».
        # Другие экраны (useRiskScores.ts, WishesView.vue myWishes/incoming)
        # зовут без status и рассчитывают именно на это.
        q = q.where(Wish.status != 'converted')
    q = q.order_by(Wish.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    wishes = result.scalars().all()

    # Phase 31: batch unseen_fields/unseen_changes_count (2 queries, no N+1) (D-05..D-09)
    wish_ids = [w.id for w in wishes]
    unseen_map: dict[int, list[str]] = {}
    try:
        from app.routers.entity_changes import get_unseen_map as _get_unseen_map
        unseen_map = await _get_unseen_map(db, 'wish', wish_ids, current_user.id)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("unseen wish map failed: %s", _exc)

    # «От кого»: имена участников (WishMember) батчем, без N+1
    members_map: dict[int, list[str]] = {}
    approvers_map: dict[int, list[str]] = {}
    purchases_map: dict[int, list[int]] = {}
    if wish_ids:
        mres = await db.execute(
            select(WishMember.wish_id, User.full_name, User.username)
            .join(User, User.id == WishMember.user_id)
            .where(WishMember.wish_id.in_(wish_ids))
        )
        for m_wid, m_fn, m_un in mres.all():
            members_map.setdefault(m_wid, []).append(m_fn or m_un)

        # «Кому»: цепочка согласующих по order_num (батчем, без N+1)
        from app.models.wish_approval import WishApproval
        ares = await db.execute(
            select(WishApproval.wish_id, User.full_name, User.username)
            .join(User, User.id == WishApproval.user_id)
            .where(WishApproval.wish_id.in_(wish_ids))
            .order_by(WishApproval.wish_id, WishApproval.order_num)
        )
        for a_wid, a_fn, a_un in ares.all():
            approvers_map.setdefault(a_wid, []).append(a_fn or a_un)

        # Конвертация разбивает заявку на несколько закупок — отдаём все id
        pres = await db.execute(
            select(Purchase.wish_id, Purchase.id)
            .where(Purchase.wish_id.in_(wish_ids))
            .order_by(Purchase.id)
        )
        for p_wid, p_id in pres.all():
            purchases_map.setdefault(p_wid, []).append(p_id)

    # Пункт 4 (владелец, 2026-08-13): сводка закупок (номер/статус/сумма) для меню
    # «Перейти в закупку» — батчем, тем же приёмом, что purchases_map выше.
    purchase_summaries_map = await _wish_purchase_summaries_map(wish_ids, db)

    # Владелец: столбец «сумма заявки» на листе /wishes — Σ total_price позиций
    # (WishItem), ОДНИМ агрегирующим запросом на всю страницу (без N+1 и без
    # загрузки всех позиций построчно).
    items_total_map: dict[int, Decimal] = {}
    if wish_ids:
        itres = await db.execute(
            select(WishItem.wish_id, func.coalesce(func.sum(WishItem.total_price), 0))
            .where(WishItem.wish_id.in_(wish_ids))
            .group_by(WishItem.wish_id)
        )
        items_total_map = {wid: total for wid, total in itres.all()}

    out_list = []
    for w in wishes:
        enriched = _enrich(w)
        enriched.member_names = members_map.get(w.id, [])
        enriched.approver_names = approvers_map.get(w.id, [])
        enriched.purchase_ids = purchases_map.get(w.id, [])
        enriched.purchases = purchase_summaries_map.get(w.id, [])
        enriched.items_total = items_total_map.get(w.id, Decimal("0"))
        _unseen = unseen_map.get(w.id, [])
        enriched.unseen_fields = _unseen
        enriched.unseen_changes_count = len(_unseen)
        out_list.append(enriched)
    return out_list


@router.get("/{wish_id}", response_model=WishOut)
async def get_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get single wish with items. Creator, assignee, or manager/admin of same org."""
    wish = await _load_wish(wish_id, db)
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")
    if current_user.role == 'employee' and wish.created_by != current_user.id and wish.assigned_to != current_user.id:
        # Check if current user is a participant (wish member)
        member_res = await db.execute(
            select(WishMember).where(
                WishMember.wish_id == wish_id,
                WishMember.user_id == current_user.id,
            )
        )
        if member_res.scalar_one_or_none() is None:
            # …или согласующий из цепочки (вкладка «На согласование мне»)
            from app.models.wish_approval import WishApproval
            appr = await db.execute(
                select(WishApproval.id).where(
                    WishApproval.wish_id == wish_id,
                    WishApproval.user_id == current_user.id,
                ).limit(1)
            )
            if appr.scalar_one_or_none() is None:
                raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    enriched = _enrich(wish)
    mnames = (await db.execute(
        select(User.full_name, User.username)
        .join(WishMember, WishMember.user_id == User.id)
        .where(WishMember.wish_id == wish_id)
    )).all()
    enriched.member_names = [fn or un for fn, un in mnames]

    from app.models.wish_approval import WishApproval
    anames = (await db.execute(
        select(User.full_name, User.username)
        .join(WishApproval, WishApproval.user_id == User.id)
        .where(WishApproval.wish_id == wish_id)
        .order_by(WishApproval.order_num)
    )).all()
    enriched.approver_names = [fn or un for fn, un in anames]
    enriched.purchase_ids = (await db.execute(
        select(Purchase.id).where(Purchase.wish_id == wish_id).order_by(Purchase.id)
    )).scalars().all()
    # Пункт 4 (владелец, 2026-08-13): номер/статус/сумма для меню «Перейти в закупку».
    enriched.purchases = (await _wish_purchase_summaries_map([wish_id], db)).get(wish_id, [])
    # items уже загружены selectinload'ом в _load_wish — суммируем в памяти,
    # без доп. запроса (см. items_total в list_wishes для батч-версии).
    enriched.items_total = sum((it.total_price or Decimal("0")) for it in (wish.items or [])) or Decimal("0")

    # W1: contracted_locked — есть ли закупка в статусе Договор+
    # Правка владельца (2026-08-18): сообщение о блокировке должно называть
    # конкретную закупку и её реальную стадию, а не всегда «Договор» — см.
    # _wish_locked_descr. contracted_locked_reason — готовая строка для баннера
    # на фронте (frontend/src/views/WishesView.vue), None если не заблокировано.
    _locked_descr = await _wish_locked_descr(wish_id, db)
    enriched.contracted_locked = bool(_locked_descr)
    enriched.contracted_locked_reason = _locked_descr

    # W-diff: «двойник» каждой позиции в закупке — только карточка, не список
    await _attach_purchase_matches(wish, enriched, db)

    # Phase 31: unseen_fields for single wish GET (D-05..D-09)
    try:
        from app.routers.entity_changes import get_unseen_map as _get_unseen_map
        _unseen_single = await _get_unseen_map(db, 'wish', [wish_id], current_user.id)
        _unseen_fields = _unseen_single.get(wish_id, [])
        enriched.unseen_fields = _unseen_fields
        enriched.unseen_changes_count = len(_unseen_fields)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("unseen wish single failed: %s", _exc)

    return enriched


@router.post("/{wish_id}/copy", response_model=WishOut, status_code=201)
async def copy_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Копирование заявки (владелец, 2026-08-13): «при переделывании больших
    заявок не приходилось делать двойную работу — могут быть однотипные заявки
    с небольшим расхождением». Создаёт НОВУЮ заявку-черновик.

    Копируется ТОЛЬКО то, что описывает сам товар — item_name/item_type/
    product_id/quantity/unit/country_origin по каждой позиции — и заголовок
    исходной заявки с пометкой «(копия)».

    НЕ копируется (владелец прямо просил дозаполнять и проверять, «куда что
    идёт»): категории ФЭО у позиций (feo_category_id), привязка к плановым
    позициям (feo_planned_item_id/match_confirmed), НДС-ставка и over_plan,
    цены (unit_price/total_price), даты потребности (needed_date), исполнитель,
    согласующие, статус, привязки к закупкам, вложения. Сама новая заявка
    всегда создаётся в статусе 'draft' (как в create_wish), автор — текущий
    пользователь.

    org_id и subsidy_id копируются «как есть» — это рамка (организация и
    бюджет), в которой человек работает, а не «куда что идёт» внутри неё.

    Права: та же проверка видимости, что в GET /{wish_id} (без доп. ролевых
    ограничений сверх неё — копировать может любой, кто видит заявку).
    """
    wish = await _load_wish(wish_id, db)
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")
    if current_user.role == 'employee' and wish.created_by != current_user.id and wish.assigned_to != current_user.id:
        member_res = await db.execute(
            select(WishMember).where(
                WishMember.wish_id == wish_id,
                WishMember.user_id == current_user.id,
            )
        )
        if member_res.scalar_one_or_none() is None:
            from app.models.wish_approval import WishApproval
            appr = await db.execute(
                select(WishApproval.id).where(
                    WishApproval.wish_id == wish_id,
                    WishApproval.user_id == current_user.id,
                ).limit(1)
            )
            if appr.scalar_one_or_none() is None:
                raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    from app.schemas.wishes import _clamp_title
    new_title = _clamp_title(f"{wish.title} (копия)")

    new_wish = Wish(
        org_id=wish.org_id,
        title=new_title,
        subsidy_id=wish.subsidy_id,
        status="draft",
        created_by=current_user.id,
    )
    db.add(new_wish)
    await db.flush()

    for it in (wish.items or []):
        db.add(WishItem(
            wish_id=new_wish.id,
            product_id=it.product_id,
            item_name=it.item_name,
            item_type=it.item_type,
            quantity=it.quantity,
            unit=it.unit,
            country_origin=it.country_origin,
        ))

    await db.commit()
    new_wish = await _load_wish(new_wish.id, db)
    enriched = _enrich(new_wish)
    enriched.items_total = sum((it.total_price or Decimal("0")) for it in (new_wish.items or [])) or Decimal("0")
    return enriched


@router.post("/", response_model=WishOut, status_code=201)
async def create_wish(
    body: WishCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new wish (all roles)."""
    from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding
    await assert_subsidy_approved_for_binding(db, body.subsidy_id)

    org_ids = get_org_filter(current_user)
    org_id = org_ids[0] if org_ids else current_user.org_id

    wish = Wish(
        org_id=org_id,
        title=body.title,
        category=body.category,
        description=body.description,
        quantity=body.quantity,
        unit=body.unit,
        estimated_price=body.estimated_price,
        link=body.link,
        priority=body.priority,
        desired_date=body.desired_date,
        justification=body.justification,
        subsidy_id=body.subsidy_id,
        feo_category_id=body.feo_category_id,
        event_id=body.event_id,
        assigned_to=body.assigned_to,
        status="draft",
        created_by=current_user.id,
        feo_per_item=body.feo_per_item,
        vat_mode=body.vat_mode or 'uniform',
    )
    db.add(wish)
    await db.flush()

    # ПРАВИЛО №6 (группа D5): единственный писатель — item_contractor.set_item_contractor.
    if body.contractor_id is not None:
        from app.models.contractor import Contractor as _Contractor
        _create_contractor = await db.get(_Contractor, body.contractor_id)
        if _create_contractor:
            set_item_contractor(wish, contractor=_create_contractor, name=body.contractor_name)
        else:
            set_item_contractor(wish, contractor_id=body.contractor_id)
    elif body.contractor_name:
        set_item_contractor(wish, name=body.contractor_name)

    if body.items:
        for item_data in body.items:
            if not _is_meaningful_item(item_data):
                continue  # пустая строка-заготовка — в БД не пишем
            wi = WishItem(
                wish_id=wish.id,
                product_id=item_data.get('product_id'),
                item_name=item_data.get('item_name', ''),
                item_type=item_data.get('item_type', 'товар'),
                quantity=item_data.get('quantity', 1),
                unit=item_data.get('unit', 'шт'),
                unit_price=item_data.get('unit_price', 0),
                total_price=item_data.get('total_price', 0),
                country_origin=item_data.get('country_origin', 'РФ'),
                feo_category_id=item_data.get('feo_category_id'),  # B9
                feo_planned_item_id=item_data.get('feo_planned_item_id'),  # привязка к плановой позиции плана закупок
                over_plan=item_data.get('over_plan', False),
                needed_date=_as_date(item_data.get('needed_date')),  # W2
                vat_rate=item_data.get('vat_rate'),
            )
            db.add(wi)
        await db.flush()

    await db.commit()
    wish = await _load_wish(wish.id, db)
    return _enrich(wish)


@router.put("/{wish_id}", response_model=WishOut)
async def update_wish(
    wish_id: int,
    body: WishUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a wish.
    Draft/rejected: full edit.
    Submitted/approved/converted: edit allowed (for all non-SaaS if not contracted-locked),
    then resets approval chain and re-notifies approvers.
    B3: contracted-locked wishes (purchase in Договор+) are read-only.
    """
    wish = await _load_wish(wish_id, db)

    if not _is_saas(current_user) and wish.created_by != current_user.id:
        # Участники заявки (WishMember) тоже могут её редактировать
        if not await _is_wish_member(wish_id, current_user.id, db):
            # Дефект 1 (владелец, 2026-08-20): согласующий из цепочки WishApproval
            # сюда попадать не должен вовсе — фронт больше не зовёт PUT для него,
            # ФЭО он правит через PATCH /execution. Но если это всё-таки произошло
            # (старый фронт/прямой запрос) — подсказать конкретно, а не молчать
            # общей фразой (feedback_explain_blocking_reason).
            from app.models.wish_approval import WishApproval
            is_chain_approver = (await db.execute(
                select(WishApproval.id).where(
                    WishApproval.wish_id == wish_id,
                    WishApproval.user_id == current_user.id,
                ).limit(1)
            )).scalar_one_or_none() is not None
            detail = "Редактировать заявку может автор или участник заявки"
            if is_chain_approver:
                detail += ". Состав заявки меняет автор — как согласующий, правьте категорию ФЭО прямо в форме (сохраняется автоматически), решение отправляйте кнопкой «Согласовать»/«Отклонить»"
            raise HTTPException(status_code=403, detail=detail)

    # W2: contracted-lock replaces old draft-only gate
    if not _is_saas(current_user):
        _locked_descr = await _wish_locked_descr(wish.id, db)
        if _locked_descr:
            raise HTTPException(
                status_code=409,
                detail=f"Заявка привязана к закупке — {_locked_descr}. Редактирование запрещено",
            )
        # SaaS is always allowed; for others allow draft/rejected AND submitted/approved/converted

    # Владелец (2026-08-13): «После согласования заявку править нельзя, только в
    # закупке» — на статусе 'converted' заявка уже в Плане закупок, единственный
    # источник правды для позиций — сама закупка (PurchaseItem), а не WishItem.
    # Раньше правка позиций тут ЧАСТИЧНО синхронизировалась в закупку
    # (_sync_wish_items_to_purchases копировал название/кол-во/цену, но НЕ
    # категорию ФЭО) — данные расходились: в заявке позиция в одной категории,
    # в закупке в другой. Теперь правка позиций конвертированной заявки
    # отклоняется явно; несущественные поля заявки (приоритет, срок и т.п.)
    # по-прежнему редактируемы — блокируются только `items`.
    if not _is_saas(current_user) and wish.status == "converted" and body.items is not None:
        _linked_purchases = await _wish_linked_purchases(wish_id, db)
        _purchase_nums = ", ".join(
            f"№{p.purchase_number or p.id}" for p in _linked_purchases
        ) or "не найдена"
        raise HTTPException(
            status_code=409,
            detail=(
                "Заявка уже в плане закупок — изменения вносятся в закупке "
                f"({_purchase_nums})"
            ),
        )

    # Capture old status BEFORE mutation
    old_status = wish.status

    # Phase 31: capture old values for diff-tracking BEFORE any mutation (D-05..D-09)
    _old_wish_values = {f: getattr(wish, f, None) for f in WISH_TRACKED_FIELDS}

    # A1 fix: снимок существенных скалярных полей ДО мутации (Дыра 2)
    # Жалоба владельца 2026-08-13: привязка позиции к категории/плановой позиции
    # ФЭО — это маршрутизация по бюджету, а не смена предмета закупки. Согласующий
    # привязывал позицию к ФЭО и нажимал «Сохранить» уже ПОСЛЕ того, как согласовал —
    # feo_category_id в этом наборе стирал его же согласование («повторное
    # согласование» без реального изменения того, ЧТО закупается). За перерасход
    # отвечают отдельные гейты (assert_no_unapproved_excess / потолок субсидии),
    # поэтому feo_category_id сюда не входит.
    _APPROVAL_SENSITIVE_FIELDS: set[str] = {
        "title", "subsidy_id", "estimated_price",
        "quantity", "unit", "justification",
    }
    _old_sensitive = {f: getattr(wish, f, None) for f in _APPROVAL_SENSITIVE_FIELDS}

    # A1 fix: снимок позиций ДО мутации для точного сравнения (Дыра 1)
    # feo_category_id намеренно НЕ входит в кортеж сравнения — см. комментарий
    # у _APPROVAL_SENSITIVE_FIELDS выше (жалоба 2026-08-13).
    _old_items = {
        wi.id: (
            str(wi.item_name or ''),
            str(wi.unit or ''),
            float(wi.quantity or 0),
            float(wi.unit_price or 0),
            float(wi.total_price or 0),
        )
        for wi in (wish.items or [])
    }

    if body.subsidy_id is not None:
        from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding
        await assert_subsidy_approved_for_binding(db, body.subsidy_id)

    update_data = body.model_dump(exclude_none=True, exclude={'items'})
    for field, value in update_data.items():
        setattr(wish, field, value)

    # Контрагент — необязательное поле (владелец, 2026-08-17), а «необязательное»
    # значит, что его можно и СНЯТЬ, не только поставить. Общий model_dump(exclude_none=True)
    # выше НЕ трогаем скопом: на нём годами держится поведение остальных Optional-полей
    # формы заявки («ключ отсутствует/null» = «не менять», привычно для частичных PUT —
    # например автосохранение одного поля не должно стирать все остальные) — массовая
    # замена на exclude_unset рисковала бы молча обнулить что-то, что никто не просил
    # чистить. Поэтому точечно, только для contractor_id/contractor_name: используем
    # body.model_fields_set — Pydantic v2 кладёт туда имя поля, если СООТВЕТСТВУЮЩИЙ КЛЮЧ
    # реально присутствовал в JSON тела запроса (даже если значение — null), и не кладёт,
    # если ключ отсутствовал вовсе. Так «прислали null» (пользователь снял контрагента)
    # отличается от «ключ не прислали» (например, автосохранение другого поля заявки —
    # значение контрагента трогать не должно).
    # ПРАВИЛО №6 (группа D5): единственный писатель контрагента — item_contractor.
    # set_item_contractor (FK — источник истины, текст обнуляется, когда FK задан).
    # Partial-update нюанс (см. комментарий выше про model_fields_set): поле,
    # которое НЕ пришло ключом в этом запросе, не трогаем — только contractor_id
    # принудительно обнуляет текст ВСЕГДА, когда сам он устанавливается ненулевым
    # (инвариант «текст только при contractor_id IS NULL» не может ждать, пока
    # придёт ещё и contractor_name отдельным запросом).
    if 'contractor_id' in body.model_fields_set:
        if body.contractor_id is not None:
            from app.models.contractor import Contractor as _Contractor
            _new_contractor = await db.get(_Contractor, body.contractor_id)
            if _new_contractor:
                set_item_contractor(
                    wish, contractor=_new_contractor,
                    name=(body.contractor_name if 'contractor_name' in body.model_fields_set else None),
                )
            else:
                # Контрагент с таким id не найден — ставим голый FK, текст всё равно NULL.
                set_item_contractor(wish, contractor_id=body.contractor_id)
        else:
            # Снятие контрагента: FK → NULL; contractor_name трогаем ТОЛЬКО если он
            # реально пришёл в этом же запросе, иначе не вносим шум в чужое поле.
            wish.contractor_id = None
            if 'contractor_name' in body.model_fields_set:
                wish.contractor_name = body.contractor_name
    elif 'contractor_name' in body.model_fields_set:
        if wish.contractor_id:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "update_wish: contractor_name=%r проигнорирован — у заявки id=%s уже задан "
                "contractor_id=%s (FK остаётся источником истины)",
                body.contractor_name, wish.id, wish.contractor_id,
            )
        else:
            wish.contractor_name = body.contractor_name

    # Плановые позиции следуют за сменой категории (владелец, 2026-08-17):
    # предупреждения, когда привязку пришлось снять вместо переезда (см. ветку
    # non-draft ниже) — возвращаются в ответе, не проглатываются молча.
    _plan_transfer_warnings: list[str] = []

    if body.items is not None:
        if old_status == "draft":
            # Draft: delete+recreate (original behaviour)
            await db.execute(delete(WishItem).where(WishItem.wish_id == wish.id))
            for item_data in body.items:
                if not _is_meaningful_item(item_data):
                    continue  # пустая строка-заготовка — в БД не пишем
                wi = WishItem(
                    wish_id=wish.id,
                    product_id=item_data.get('product_id'),
                    item_name=item_data.get('item_name', ''),
                    item_type=item_data.get('item_type', 'товар'),
                    quantity=item_data.get('quantity', 1),
                    unit=item_data.get('unit', 'шт'),
                    unit_price=item_data.get('unit_price', 0),
                    total_price=item_data.get('total_price', 0),
                    country_origin=item_data.get('country_origin', 'РФ'),
                    feo_category_id=item_data.get('feo_category_id'),  # B9
                    feo_planned_item_id=item_data.get('feo_planned_item_id'),  # план закупок ФЭО
                    over_plan=item_data.get('over_plan', False),
                    needed_date=_as_date(item_data.get('needed_date')),  # W2
                    vat_rate=item_data.get('vat_rate'),
                )
                db.add(wi)
            await db.flush()
        else:
            # Non-draft (submitted/approved/converted/rejected): update existing items in-place by id,
            # and DELETE items that dropped out of the payload (owner removes a duplicate/empty row →
            # it must actually disappear from the DB, not just from the UI). Add is still NOT
            # supported here — out of scope, unchanged from prior behaviour (items without a
            # matching id are silently skipped).
            existing_items = {wi.id: wi for wi in wish.items}
            payload_ids: set[int] = set()
            for item_data in body.items:
                item_id = item_data.get('id') if isinstance(item_data, dict) else getattr(item_data, 'id', None)
                if item_id:
                    payload_ids.add(item_id)
                wi = existing_items.get(item_id) if item_id else None
                if wi is None:
                    continue
                if 'item_name' in item_data:
                    wi.item_name = item_data['item_name']
                if 'unit_price' in item_data:
                    wi.unit_price = item_data['unit_price']
                if 'quantity' in item_data:
                    wi.quantity = item_data['quantity']
                if 'unit' in item_data:
                    wi.unit = item_data['unit']
                if 'total_price' in item_data:
                    wi.total_price = item_data['total_price']
                elif 'unit_price' in item_data or 'quantity' in item_data:
                    wi.total_price = (wi.unit_price or 0) * (wi.quantity or 0)
                _wi_cat_changing = (
                    'feo_category_id' in item_data
                    and item_data['feo_category_id'] != wi.feo_category_id
                )
                if 'feo_category_id' in item_data:
                    wi.feo_category_id = item_data['feo_category_id']
                if 'feo_planned_item_id' in item_data:
                    # Явный выбор плановой позиции с фронта (в т.ч. её очистка) —
                    # доверяем как есть, автоперенос ниже не запускаем.
                    wi.feo_planned_item_id = item_data['feo_planned_item_id']
                elif _wi_cat_changing and wi.feo_planned_item_id is not None:
                    # Плановые позиции следуют за сменой категории (владелец,
                    # 2026-08-17): payload сменил feo_category_id позиции, но не
                    # прислал новый feo_planned_item_id явно — старая привязка
                    # осталась указывать на прежнюю категорию. Если позиция —
                    # единственный владелец своей плановой строки, строка
                    # переезжает вместе с ней; если план общий с другими
                    # закупками/заявками — привязка снимается и предупреждение
                    # копится в _plan_transfer_warnings (возвращается в ответе).
                    if wi.feo_category_id is not None:
                        _w = await _move_or_detach_planned_item(db, wi, wi.feo_category_id)
                        if _w:
                            _plan_transfer_warnings.append(_w)
                    else:
                        # Категория очищена целиком — плановой позиции
                        # переезжать некуда, привязка просто снимается.
                        from app.models.feo_planned_item import FeoPlannedItem as _FPI2
                        from app.services.plan_autoassign import deactivate_if_orphaned as _deactivate_if_orphaned
                        _old_fpi2 = await db.get(_FPI2, wi.feo_planned_item_id)
                        wi.feo_planned_item_id = None
                        wi.over_plan = False
                        await _deactivate_if_orphaned(db, _old_fpi2)
                if 'over_plan' in item_data:
                    wi.over_plan = item_data['over_plan']
                if 'needed_date' in item_data:
                    wi.needed_date = _as_date(item_data['needed_date'])
                if 'vat_rate' in item_data:
                    wi.vat_rate = item_data['vat_rate']

                # Шаг 5 «цена ТЗ не выше плановой» (владелец, 2026-08-07): правка
                # заявки — тот же обход, что и _sync_wish_items_to_purchases выше,
                # проверяем ЗДЕСЬ (на WishItem), т.к. именно отсюда цена/кол-во
                # затем копируются в PurchaseItem. over_plan=true пропускаем —
                # сознательно сверх плана.
                if ('unit_price' in item_data or 'quantity' in item_data) and not getattr(wi, 'over_plan', False):
                    await assert_tz_not_over_plan(
                        db,
                        feo_planned_item_id=wi.feo_planned_item_id,
                        feo_category_id=wi.feo_category_id,
                        quantity=wi.quantity,
                        unit_price=wi.unit_price,
                        total_price=wi.total_price,
                        item_name=wi.item_name,
                    )

            # Позиции, которых больше нет в payload, — удаляем физически.
            ids_to_delete = set(existing_items.keys()) - payload_ids
            if ids_to_delete:
                _locked_descr = await _wish_locked_descr(wish.id, db)
                if _locked_descr:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Нельзя удалить позицию заявки: закупка {_locked_descr} уже на этапе "
                            "договора. Отмените закупку вручную в реестре закупок, либо не удаляйте позицию."
                        ),
                    )
                # Сироты в закупке: PurchaseItem с FK на удаляемую позицию (ondelete=SET NULL
                # только обнулит связь, но НЕ уберёт строку) — чистим явно, но только пока
                # закупка ещё не ушла дальше «Плана закупок» (иначе выше сработал бы гейт).
                _linked_purchases = await _wish_linked_purchases(wish.id, db)
                _early_stage_purchase_ids = {
                    p.id for p in _linked_purchases if p.status in ("plan_schedule", "wishes")
                }
                if _early_stage_purchase_ids:
                    await db.execute(
                        delete(PurchaseItem).where(
                            PurchaseItem.wish_item_id.in_(ids_to_delete),
                            PurchaseItem.purchase_id.in_(_early_stage_purchase_ids),
                        )
                    )
                # Удаляем через саму relationship-коллекцию (cascade="all, delete-orphan" на
                # Wish.items), а не Core delete(): так wish.items остаётся синхронной в памяти
                # для последующего сравнения _old_items/_new_items (сброс согласования ниже).
                for _del_id in ids_to_delete:
                    wish.items.remove(existing_items[_del_id])

            await db.flush()

    # W2: re-approval trigger for submitted/approved/converted wishes
    # A1 fix: сбрасываем согласование ТОЛЬКО при изменении существенных полей.
    # Существенные поля = те, что определяют предмет закупки и требуют повторного
    # одобрения согласующих. Несущественные (priority, desired_date, event_id,
    # assigned_to, executor_id, execution_deadline, link) НЕ сбрасывают цепочку.
    if old_status in ("submitted", "approved", "converted"):
        # Дыра 2 исправлена: используем _old_sensitive (снят ДО мутации) вместо
        # _old_wish_values (который содержит только WISH_TRACKED_FIELDS, без quantity/unit/justification).
        _sensitive_changed = any(
            str(_old_sensitive.get(f)) != str(getattr(wish, f, None))
            for f in _APPROVAL_SENSITIVE_FIELDS
        )
        # Дыра 1 исправлена: сравниваем реальное содержимое позиций до/после.
        # Фронт всегда шлёт body.items, поэтому «items is not None» — недостаточное условие.
        # feo_category_id намеренно НЕ входит — привязка к ФЭО/плановой позиции не
        # меняет предмет закупки, это маршрутизация по бюджету (жалоба 2026-08-13).
        _new_items = {
            wi.id: (
                str(wi.item_name or ''),
                str(wi.unit or ''),
                float(wi.quantity or 0),
                float(wi.unit_price or 0),
                float(wi.total_price or 0),
            )
            for wi in (wish.items or [])
        }
        _items_changed = (_old_items != _new_items)

        if _sensitive_changed or _items_changed:
            # Проверяем наличие согласующих ДО смены статуса (старые заявки могли быть одобрены без цепочки)
            from app.models.wish_approval import WishApproval as _WA
            _approver_count = (await db.execute(
                select(func.count()).select_from(_WA).where(_WA.wish_id == wish.id)
            )).scalar() or 0
            if _approver_count == 0:
                raise HTTPException(
                    status_code=409,
                    detail="Заявка уйдёт на повторное согласование, но согласующие не выбраны — "
                           "добавьте хотя бы одного согласующего в разделе «Согласующие».",
                )
            # W2: проверяем плановые даты перед сбросом в submitted (авансовые пропускаем)
            if getattr(wish, 'source', None) != 'advance_report':
                await _ensure_needed_dates(wish, db, wish.items or [], context="submit")
            wish.status = "submitted"
            # Повторная отправка на согласование после правки — старое
            # отклонение больше не актуально (владелец, 2026-08-19).
            wish.rejected_by = None
            wish.rejected_at = None
            wish.rejection_reason = None
            await db.flush()
            await _reset_approvals(wish.id, db)
            # Заявка уходит на ПОВТОРНОЕ согласование — позиции могли измениться,
            # закупка в Плане закупок больше не актуальна, убираем её оттуда. Если что-то
            # уже в работе/договоре — откат запрещаем явно (не молчим, коммита ещё не было).
            await _withdraw_wish_from_plan(wish.id, db, action_text="вернуть на повторное согласование")
            requester_name = getattr(current_user, 'full_name', None) or current_user.username
            await _notify_pending_approvers(wish, db, requester_name)

    await db.commit()

    # Phase 31: record EntityChange for each TRACKED_FIELD that changed (D-05..D-09)
    # Only record changes made by OTHER users (D-07: own changes are not highlighted)
    try:
        from app.models.entity_change import EntityChange as _EC
        _changes = []
        for _fname in WISH_TRACKED_FIELDS:
            _old = _old_wish_values.get(_fname)
            _new = getattr(wish, _fname, None)
            _old_s = str(_old) if _old is not None else None
            _new_s = str(_new) if _new is not None else None
            if _old_s != _new_s:
                _changes.append(_EC(
                    entity_type='wish',
                    entity_id=wish.id,
                    field_name=_fname,
                    old_value=_old_s,
                    new_value=_new_s,
                    changed_by_id=current_user.id,
                    changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                ))
        if _changes:
            for _c in _changes:
                db.add(_c)
            await db.commit()
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("entity_change record failed for wish: %s", _exc)

    wish = await _load_wish(wish_id, db)
    out = _enrich(wish)
    out.plan_transfer_warnings = _plan_transfer_warnings
    return out


@router.delete("/{wish_id}", status_code=204)
async def delete_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a draft wish (creator only)."""
    wish = await _load_wish(wish_id, db)

    if not _is_saas(current_user) and wish.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Только автор может удалить заявку")
    if not _is_saas(current_user) and wish.status != "draft":
        raise HTTPException(status_code=400, detail="Можно удалить только черновик")

    # Заявку удаляют — purchases.wish_id обнулится каскадом (ON DELETE SET NULL),
    # закупка осиротеет в плане. Плановые (plan_schedule) убираем из плана заранее;
    # если что-то уже в работе/договоре — удаление блокируем явно (владелец, 2026-08-07).
    await _withdraw_wish_from_plan(wish.id, db, action_text="удалить")

    await db.delete(wish)
    await db.commit()


@router.patch("/{wish_id}/items/{item_id}")
async def patch_wish_item(
    wish_id: int,
    item_id: int,
    body: WishItemPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """D-04: Drag-drop target update. Scoped to wish — cannot move items between wishes.

    Returns 409 if wish уже распределена (converted) — read-only.
    Returns 404 if item does not belong to wish_id.

    Владелец (2026-09-04, заявка №55): гейт раньше блокировал перенос уже на статусе
    'approved', хотя /approve-distribution (app/routers/wish_convert.py) на этом
    статусе распределение ещё РАЗРЕШАЕТ — пользователь видел кнопку «Распределить
    и одобрить», но перетащить ничего не мог (409 «уже одобрена»). Статус, после
    которого распределение зафиксировано и правда нельзя менять — 'converted'
    (создались закупки), поэтому гейт здесь приведён в соответствие с
    approve_distribution: draft/submitted/approved — редактируемо, converted —
    только чтение.
    """
    wish = await _load_wish(wish_id, db)
    if not _is_saas(current_user) and wish.status not in ("draft", "submitted", "approved"):
        raise HTTPException(status_code=409, detail="Заявка уже распределена — редактирование запрещено")
    # Find item BELONGING TO THIS WISH
    item = next((i for i in wish.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Позиция не найдена в данной заявке")
    # body.target_column_key may be None (clear) or a non-empty string (override)
    item.target_column_key = body.target_column_key
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "target_column_key": item.target_column_key}

