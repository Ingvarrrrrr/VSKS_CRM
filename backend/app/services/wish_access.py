"""Проверки доступа/членства и гейты заявки (Wish) перед мутирующими переходами.

Вынесено из app/routers/wishes.py (Правило №5, модульность; сессия 2026-09-08,
вторая резка wishes.py по образцу первой — commit 89187a0 — и users.py →
commit ca7b02c) БЕЗ ИЗМЕНЕНИЯ ПОВЕДЕНИЯ.

app/routers/wishes.py импортирует всё отсюда на уровне модуля (для re-export —
потребители вроде app/routers/wish_convert.py и app/routers/wish_transitions.py
зовут эти имена через `wishes_core.<имя>`, см. докстринг wish_transitions.py
про monkeypatch). Обратной зависимости на уровне модуля здесь НЕТ — этот файл
импортирует `_is_saas` из app/routers/wishes.py ЛЕНИВО (внутри функции), тем же
приёмом, каким app/services/wish_distribution.py тянет хелперы ядра, — иначе
получился бы цикл wishes.py → wish_access.py → wishes.py.
"""
from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import MANAGER_ROLES
from app.models.wish_member import WishMember
from app.models.purchase import Purchase


# W1: статусы «дошли до договора» — блокируют редактирование привязанной заявки
CONTRACTED_STATUSES = ("contracted", "ordered", "delivered", "paid")


async def _wish_linked_purchases(wish_id: int, db: AsyncSession) -> list:
    """Возвращает список закупок, привязанных к заявке."""
    res = await db.execute(select(Purchase).where(Purchase.wish_id == wish_id))
    return res.scalars().all()


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
    from datetime import timezone
    from app.models.wish_approval import WishApproval
    # Ленивый импорт во избежание цикла wishes.py → wish_access.py → wishes.py
    # (см. докстринг модуля) — тем же приёмом, каким app/services/wish_distribution.py
    # тянет хелперы ядра.
    from app.routers.wishes import _is_saas
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
