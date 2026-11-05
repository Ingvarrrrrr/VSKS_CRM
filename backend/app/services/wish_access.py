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


def wish_purchase_delete_blockers(purchases: list) -> list[str]:
    """Закупки заявки, дошедшие до договора (contracted/ordered/delivered/paid) —
    блокируют и откат заявки в черновик (_withdraw_wish_from_plan), и полное
    удаление заявки (delete_wish, 29.10.2026). Статусы ДО договора
    (RETURNABLE_TO_WISH_STATUSES: plan_schedule и work_in_progress «Ведётся
    работа» — выставлена на площадку, до подписания договора) откат не
    блокируют и возвращаются в 'wishes' (ПРАВИЛО №6, согласовано с
    app/services/purchase_return_to_wish.py::RETURNABLE_TO_WISH_STATUSES)."""
    from app.routers.purchase_budget import PLANNED_STATUSES
    from app.routers.purchase_export import _STATUS_LABELS
    from app.services.purchase_label import purchase_label
    from app.services.purchase_return_to_wish import ALLOWED_STATUSES as RETURNABLE_TO_WISH_STATUSES

    blockers: list[str] = []
    for p in purchases:
        if p.status not in RETURNABLE_TO_WISH_STATUSES and p.status in PLANNED_STATUSES:
            label = _STATUS_LABELS.get(p.status, p.status)
            blockers.append(f"{purchase_label(p)} «{p.item_name or ''}» на стадии «{label}»")
    return blockers


async def _is_wish_member(wish_id: int, user_id: int, db: AsyncSession) -> bool:
    res = await db.execute(
        select(WishMember.id).where(
            WishMember.wish_id == wish_id,
            WishMember.user_id == user_id,
        ).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def ensure_wish_read_access(wish, current_user, db: AsyncSession) -> None:
    """403, если у пользователя нет доступа к чтению заявки.

    Извлечено БЕЗ ИЗМЕНЕНИЯ ПОВЕДЕНИЯ из routers/wishes.py::get_wish (2026-09-21,
    W3) — GET /api/wishes/{id}/tz-rows нуждается ровно в той же проверке
    («Права — как у чтения заявки»), заводить вторую копию нельзя (Правило №6).
    get_wish теперь тоже зовёт эту функцию.

    Правила: org isolation по get_org_filter; дальше — creator/assignee/
    manager+ проходят всегда; employee — только участник (WishMember) или
    согласующий из цепочки (WishApproval).
    """
    from app.auth.jwt import get_org_filter
    from app.models.wish_approval import WishApproval

    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")
    if current_user.role == 'employee' and wish.created_by != current_user.id and wish.assigned_to != current_user.id:
        member_res = await db.execute(
            select(WishMember.id).where(
                WishMember.wish_id == wish.id,
                WishMember.user_id == current_user.id,
            ).limit(1)
        )
        if member_res.scalar_one_or_none() is None:
            appr = await db.execute(
                select(WishApproval.id).where(
                    WishApproval.wish_id == wish.id,
                    WishApproval.user_id == current_user.id,
                ).limit(1)
            )
            if appr.scalar_one_or_none() is None:
                raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")


async def ensure_wish_write_access(wish, current_user, db: AsyncSession) -> None:
    """403, если пользователь не может РЕДАКТИРОВАТЬ заявку (не только читать).

    Извлечено из app/routers/wishes.py::update_wish (ядро гейта «кто правит
    заявку» — SaaS/автор/участник, без embellishment-текста про согласующего
    из цепочки, который относится только к форме PUT и остаётся инлайн там) —
    ПРАВИЛО №6: второй источник этой проверки не заводим, update_wish
    оставлен как есть (его инлайн-версия добавляет точечную подсказку для
    согласующего — трогать wishes.py вне объёма задачи рискованно, см. отчёт
    задачи «Добавить забытое из субсидии», 29.10.2026). Новые вызывающие
    (app/services/wish_append_from_plan.py) зовут эту функцию, не копию."""
    await ensure_wish_read_access(wish, current_user, db)
    from app.routers.wishes import _is_saas
    if _is_saas(current_user) or wish.created_by == current_user.id:
        return
    if await _is_wish_member(wish.id, current_user.id, db):
        return
    raise HTTPException(status_code=403, detail="Редактировать заявку может автор или участник заявки")


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

    is_advance = getattr(wish, "source", None) == "advance_report"
    per_item = bool(getattr(wish, "feo_per_item", False))
    wish_cat_id = wish.feo_category_id
    ref_ids = {i for i in ({wish_cat_id} | {_item_field(it, 'feo_category_id') for it in items}) if i}
    valid_cats: dict[int, FeoCategory] = {}
    parent_ids: set[int] = set()
    if ref_ids:
        cat_rows = (await db.execute(
            select(FeoCategory).where(FeoCategory.id.in_(ref_ids))
        )).scalars().all()
        valid_cats = {c.id: c for c in cat_rows}
        if is_advance:
            parent_ids = set((await db.execute(
                select(FeoCategory.parent_id).where(FeoCategory.parent_id.in_(ref_ids))
            )).scalars().all())

    valid_ids = set(valid_cats.keys())
    wish_cat_ok = wish_cat_id is None or wish_cat_id in valid_ids
    problem_names: list[str] = []
    problem_ids: list[int] = []
    undetermined_names: list[str] = []
    non_leaf_names: list[str] = []
    for it in items:
        item_cat = _item_field(it, 'feo_category_id')
        eff_cat = (item_cat or wish_cat_id) if per_item else (wish_cat_id or item_cat)
        item_name_str = str(_item_field(it, 'item_name') or 'без названия')
        item_id_val = _item_field(it, 'id')
        if eff_cat is None or eff_cat not in valid_ids:
            problem_names.append(item_name_str)
            if item_id_val is not None:
                problem_ids.append(int(item_id_val))
        elif is_advance:
            cat_obj = valid_cats[eff_cat]
            cat_name_norm = (cat_obj.name or "").strip().lower()
            if cat_name_norm.startswith("не определена"):
                problem_names.append(item_name_str)
                undetermined_names.append(item_name_str)
                if item_id_val is not None:
                    problem_ids.append(int(item_id_val))
            elif eff_cat in parent_ids:
                problem_names.append(item_name_str)
                non_leaf_names.append(item_name_str)
                if item_id_val is not None:
                    problem_ids.append(int(item_id_val))

    if not problem_names and wish_cat_ok:
        return

    names_list = ", ".join(f'«{n}»' for n in problem_names[:10])
    suffix = f" и ещё {len(problem_names) - 10} поз." if len(problem_names) > 10 else ""
    parts: list[str] = []
    if problem_names:
        if is_advance and (undetermined_names or non_leaf_names):
            parts.append(
                f"у следующих позиций авансового отчёта не выбрана конкретная конечная категория ФЭО "
                f"(указана «Не определена» или промежуточная папка): {names_list}{suffix}"
            )
        else:
            parts.append(
                f"у следующих позиций нет категории ФЭО, либо она ссылается на удалённую "
                f"из справочника категорию: {names_list}{suffix}"
            )
    if not wish_cat_ok:
        parts.append(
            "категория ФЭО самой заявки была удалена из справочника "
            "(структуру ФЭО субсидии пересоздавали)"
        )
    if is_advance:
        message = (
            "Невозможно согласовать авансовый отчёт: " + "; ".join(parts) + ". "
            "Для авансового отчёта плановые позиции создаются автоматически, но необходимо выбрать "
            "конечную категорию ФЭО, в которой они будут созданы — единую для всего отчёта или "
            "отдельную для каждой позиции (переключатель «Разные категории ФЭО для каждого товара»)."
        )
    else:
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
            "missing_item_ids": problem_ids,
            "missing_item_names": problem_names,
        },
    )


async def _ensure_planned_items_assigned(wish, items, db: AsyncSession) -> None:
    """Жёсткий гейт «без выбора плановых позиций заявку нельзя окончательно согласовать» (владелец, 2026-11-05).

    Реальный случай с прода: заявка №247 «Стенды с брендирование ВСКС» была согласована
    без выбранных плановых позиций у товаров (feo_planned_item_id = None), после чего
    автозаведение создало плановые позиции из самих же строк заявки, и сравнение плана
    с ТЗ показало 0 ₽ превышения. Без явного выбора плановых позиций (существующих
    или созданных кнопкой «Создать в плане закупок») до финального согласования
    согласующий не может понять, превышает ли заявка план или всё в норме.

    Авансовые отчёты (source == 'advance_report') освобождены от ручного выбора плановых
    позиций — для них плановые позиции создаются автоматически в выбранных категориях ФЭО
    (выбор самих конечных категорий ФЭО проверяет _ensure_feo_categories_assigned).
    Листовая категория ФЭО с собственным ручным планом (planned_quantity * planned_amount > 0)
    сама выступает плановой позицией в /feo-categories/plan-positions (kind='plan_position'
    или 'feo_article', feo_planned_item_id при её выборе остаётся None).
    """
    if getattr(wish, "source", None) == "advance_report":
        return
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.feo_category import FeoCategory

    wish_cat_id = wish.feo_category_id
    planned_ids = {
        i for i in (_item_field(it, "feo_planned_item_id") for it in items) if i is not None
    }
    valid_planned_ids: set[int] = set()
    if planned_ids:
        valid_planned_ids = set((await db.execute(
            select(FeoPlannedItem.id).where(
                FeoPlannedItem.id.in_(planned_ids),
                FeoPlannedItem.is_active == True,
            )
        )).scalars().all())

    cat_ids = {
        i for i in ({wish_cat_id} | {_item_field(it, "feo_category_id") for it in items}) if i is not None
    }
    leaf_plan_cat_ids: set[int] = set()
    if cat_ids:
        cats = (await db.execute(
            select(FeoCategory).where(FeoCategory.id.in_(cat_ids))
        )).scalars().all()
        children_parents = set((await db.execute(
            select(FeoCategory.parent_id).where(FeoCategory.parent_id.in_(cat_ids))
        )).scalars().all())
        for c in cats:
            if c.id not in children_parents:
                qty = float(c.planned_quantity) if c.planned_quantity is not None else 0.0
                amt = float(c.planned_amount) if c.planned_amount is not None else 0.0
                if qty * amt > 0:
                    leaf_plan_cat_ids.add(c.id)

    problem_ids: list[int] = []
    problem_names: list[str] = []
    for it in items:
        if not _is_meaningful_item(it):
            continue
        pid = _item_field(it, "feo_planned_item_id")
        if pid is not None and pid in valid_planned_ids:
            continue
        eff_cat = _item_field(it, "feo_category_id") or wish_cat_id
        if pid is None and eff_cat is not None and eff_cat in leaf_plan_cat_ids:
            continue
        item_id = _item_field(it, "id")
        if item_id is not None:
            problem_ids.append(int(item_id))
        problem_names.append(str(_item_field(it, "item_name") or "без названия"))

    if not problem_names:
        return

    names_list = ", ".join(f"«{n}»" for n in problem_names[:10])
    suffix = f" и ещё {len(problem_names) - 10} поз." if len(problem_names) > 10 else ""
    message = (
        f"Невозможно согласовать заявку и перенести её в План закупок: "
        f"у следующих позиций не выбрана плановая позиция плана закупок: {names_list}{suffix}. "
        f"Без выбора плановых позиций нельзя определить, превышает ли заявка план или всё в норме. "
        f"Выберите существующую плановую позицию в строке товара (или кнопкой «Привязать к плану»), "
        f"либо создайте новую кнопкой «Создать в плане закупок»."
    )
    raise HTTPException(
        status_code=409,
        detail={
            "message": message,
            "error_code": "missing_planned_items",
            "missing_item_ids": problem_ids,
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
    """Строка-заготовка (без названия, количества и суммы) или обнулённая позиция
    (quantity явно задан <= 0 при нулевой сумме, например «было 10 БОП стало 0») —
    в БД, План закупок и в гейты они попадать не должны.
    Принимает как ORM WishItem, так и «сырой» dict из body.items."""
    name = _item_field(it, "item_name") or ""
    raw_qty = _item_field(it, "quantity")
    raw_total = _item_field(it, "total_price")
    qty_val = float(raw_qty or 0)
    total_val = float(raw_total or 0)
    if raw_qty is not None and qty_val <= 0 and total_val <= 0:
        return False
    return bool(str(name).strip() or qty_val > 0 or total_val > 0)


async def _wish_locked_descr(wish_id: int, db: AsyncSession) -> Optional[str]:
    """Человекочитаемое описание закупок, из-за которых заявка заблокирована
    для правки (Договор+) — None, если блокирующих закупок нет.

    Владелец увидел на проде сообщение «на этапе «Договор»» для закупки в
    статусе `ordered` («Заказано») — CONTRACTED_STATUSES шире одного статуса
    «Договор» (contracted/ordered/delivered/paid), а текст называл только его.
    Единый хелпер вместо копипасты формата в двух местах (409 при PUT и при
    удалении позиций) — чтобы формулировка не расходилась. Формат каждой
    закупки: `{purchase_label(p)} «{item_name}» — стадия «{label}»`.

    Номер закупки — через purchase_label (app/services/purchase_label.py,
    ПРАВИЛО №6, 2026-09-30): раньше здесь стоял `p.purchase_number or p.id` —
    purchase_number почти всегда NULL (легаси-поле), владелец не мог найти
    закупку по показанному числу (заявка №68 → «закупка 631», которой нет в
    реестре). purchase_label отдаёт registry_number первым приоритетом.
    """
    from app.routers.purchase_export import _STATUS_LABELS
    from app.services.purchase_label import purchase_label
    purchases = await _wish_linked_purchases(wish_id, db)
    locked = [p for p in purchases if p.status in CONTRACTED_STATUSES]
    if not locked:
        return None
    return "; ".join(
        f"{purchase_label(p)} «{p.item_name or ''}» — стадия «{_STATUS_LABELS.get(p.status, p.status)}»"
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
