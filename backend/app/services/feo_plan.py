"""feo_plan.py — единый расчёт «расхода плана» по дереву ФЭО.

Вынесено из _calculate_feo_planned_tree_bulk (app/routers/subsidies.py) и
GET /api/feo-planned-items/residuals, чтобы формула не расходилась между
эндпоинтами KPI субсидий (subsidies.py) и справочником плановых позиций
(feo_categories.py /plan-positions).

⚠️ Изоляция субсидий (сессия 2026-08-05): позиция закупки учитывается ТОЛЬКО
если Purchase.subsidy_id совпадает с subsidy_id той FeoCategory, к которой
она фактически отнесена (COALESCE(PurchaseItem.feo_category_id,
Purchase.feo_category_id)). Раньше _calculate_feo_planned_tree_bulk проверял
лишь «Purchase.subsidy_id ∈ запрошенный батч subsidy_ids» и «категория ∈
категории запрошенного батча» — НЕЗАВИСИМО друг от друга. Из-за этого закупка
субсидии A с feo_category_id, указывающей в дерево субсидии B (в т.ч. когда
Purchase.subsidy_id вовсе NULL — не совпадает ни с чем), прибавлялась к
«Запланировано» субсидии B, если та просто присутствовала в том же батче.
Результат зависел от состава батча (на проде разъезжалось: батч по всем
субсидиям давал 6 201 370.73, одиночный вызов для subsidy_id=7 — 6 188 648.23,
расхождение 12 722.50 на 3 позициях). Каждая субсидия обязана считать только
свои вкладки — деньги не должны «перепрыгивать» между субсидиями.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_item import ContractItem
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish
from app.models.wish_item import WishItem

# «Заказано» и дальше — закупка уже реально размещена (в отличие от plan_schedule/
# work_in_progress/contracted, которые ещё черновик плана закупок). FACT_CONFIRMED_STATUSES —
# подтверждено закрывающим актом (delivered/paid), ORDERED_STATUSES — все три вместе.
FACT_CONFIRMED_STATUSES: set = {"delivered", "paid"}
ORDERED_STATUSES: set = {"ordered"} | FACT_CONFIRMED_STATUSES

# Задача владельца «план ≠ факт» (сессия 2026-08-06, план zany-fluttering-mountain.md,
# шаг «A»): факт (цена по итогам КП/торгов) учитывается уже с «Ведётся работа» — как
# только заполнены договорные позиции (ContractItem) или purchases.contract_price,
# ещё ДО подписания договора (превентивный контроль, см. assert_no_unapproved_excess).
# Раньше порог был только "ordered". НЕ путать с purchase_budget.FACT_STATUSES —
# тот управляет другим порогом (панель «план vs факт» показывает факт с «Заказано» —
# владелец описывал это ДО текущей задачи, см. purchase_budget.py комментарий) и его
# трогать не просили.
FACT_PRICED_STATUSES: set = {"work_in_progress", "contracted", "ordered"}
# Все статусы, где purchase_item_fact_amount способен вернуть не-None (используется
# fact_consumption_by_category / ordered_consumption_by_category).
FACT_ELIGIBLE_STATUSES: set = FACT_PRICED_STATUSES | FACT_CONFIRMED_STATUSES
_CENTS = Decimal("0.01")


def purchase_item_fact_amount(
    pi: PurchaseItem,
    purchase: Purchase,
    ratio: Decimal,
    items_count: int,
    contract_item_total: Optional[Decimal] = None,
) -> tuple[Optional[Decimal], bool]:
    """Единая формула «фактической суммы» позиции закупки.

    Источник правды — GET /api/feo-planned-items/comparison (карточка сравнения
    план/факт), вынесено сюда, чтобы её переиспользовал и расчёт плановой суммы
    (ordered_consumption_by_category / fact_consumption_by_category ниже) — суммы
    не должны расходиться между несколькими местами (сессия 2026-08-05/2026-08-06).

    Приоритет источников факта (задача владельца, сессия 2026-08-06):
      1. contract_item_total — ContractItem.total, ТОЧНО сопоставленный этой позиции
         через source_item_id (без пропорции — предпочтительнее, т.к. известна
         именно ЭТА строка договора, а не доля от суммы закупки). Передаётся
         вызывающим кодом (предзапрошен по PurchaseItem.id, см. ordered_consumption_by_category/
         fact_consumption_by_category) — сама функция БД не читает.
      2. final_total — сумма по закрывающим документам, если уже импортирована.
      3. пропорция от purchases.contract_price (work_in_progress/contracted/ordered)
         либо purchases.acceptance_doc_amount (delivered/paid) — по доле позиции
         в сумме всех позиций закупки (ratio).
      Ничего из этого нет → факта ещё нет, fact_amount=None (для delivered/paid —
      исключение, см. ниже, сохранён старый фолбэк на total_price, т.к. эта стадия
      подтверждена актом приёмки и факт обязан существовать).

    Порог статуса (задача владельца «план ≠ факт», 2026-08-06): опущен с «Заказано»
    до «Ведётся работа» (FACT_PRICED_STATUSES = work_in_progress/contracted/ordered) —
    как только заполнены договорные позиции или contract_price, это уже ФАКТ, ещё до
    подписания договора (превентивный контроль превышения). «Поставлено»/«Оплачено» —
    подтверждено актом приёмки (final_total, иначе доля acceptance_doc_amount, иначе
    total_price — старое поведение, не меняется).

    ratio — доля позиции в сумме ВСЕХ позиций закупки (для пропорционального
    распределения суммы уровня закупки между позициями, когда позиций
    несколько — см. вызывающий код). Возвращает (fact_amount, fact_allocated) —
    fact_allocated=True, если сумма получена делением суммы закупки
    пропорционально (а не берётся напрямую).
    """
    if purchase.status in FACT_PRICED_STATUSES:
        if contract_item_total is not None:
            return contract_item_total, False
        if pi.final_total is not None:
            return Decimal(str(pi.final_total)), False
        if purchase.contract_price is not None:
            contract_price = Decimal(str(purchase.contract_price))
            amt = (contract_price * ratio).quantize(_CENTS) if items_count > 1 else contract_price
            return amt, items_count > 1
        # Нет ни строки договора, ни contract_price — факта ещё нет (текущее
        # поведение plan_schedule: возвращаем None, а не total_price).
        return None, False
    if purchase.status in FACT_CONFIRMED_STATUSES:
        if contract_item_total is not None:
            return contract_item_total, False
        if pi.final_total is not None:
            return Decimal(str(pi.final_total)), False
        if purchase.acceptance_doc_amount is not None:
            doc_amount = Decimal(str(purchase.acceptance_doc_amount))
            amt = (doc_amount * ratio).quantize(_CENTS) if items_count > 1 else doc_amount
            return amt, items_count > 1
        return Decimal(str(pi.total_price or 0)), False
    # plan_schedule — это ещё ПЛАН, факта нет.
    return None, False


async def _contract_item_totals(db: AsyncSession, item_ids) -> dict:
    """{purchase_item_id: Σ ContractItem.total} по source_item_id — приоритет №1
    формулы факта (purchase_item_fact_amount). Сумма (не последняя строка), на
    случай если по одной позиции ТЗ создано несколько строк договора."""
    item_ids = list(item_ids)
    if not item_ids:
        return {}
    rows = (await db.execute(
        select(ContractItem.source_item_id, func.coalesce(func.sum(ContractItem.total), 0))
        .where(ContractItem.source_item_id.in_(item_ids))
        .group_by(ContractItem.source_item_id)
    )).all()
    return {r[0]: Decimal(str(r[1])) for r in rows if r[1]}


async def _purchase_item_totals(db: AsyncSession, purchase_ids) -> dict:
    """{purchase_id: (items_count, Σ total_price)} — знаменатель для пропорционального
    распределения (ratio) суммы уровня закупки между её позициями."""
    purchase_ids = list(purchase_ids)
    if not purchase_ids:
        return {}
    rows = (await db.execute(
        select(
            PurchaseItem.purchase_id,
            func.count(PurchaseItem.id),
            func.coalesce(func.sum(PurchaseItem.total_price), 0),
        )
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
        .group_by(PurchaseItem.purchase_id)
    )).all()
    return {r[0]: (r[1], Decimal(str(r[2] or 0))) for r in rows}


async def plan_consumption_by_category(
    db: AsyncSession,
    subsidy_ids: list[int],
    exclude_planned_item_linked: bool = False,
) -> dict[int, dict]:
    """{feo_category_id: {consumed, consumed_quantity, over, over_quantity}}

    Суммы позиций закупок в PLANNED_STATUSES, отнесённых к конечному элементу
    дерева ФЭО (COALESCE(PurchaseItem.feo_category_id, Purchase.feo_category_id)),
    разложенные по признаку PurchaseItem.over_plan:
      over_plan=false → consumed / consumed_quantity (расходует план элемента)
      over_plan=true  → over / over_quantity (сверх плана, прибавляется поверх)

    Изоляция субсидий: строка учитывается только если Purchase.subsidy_id ==
    FeoCategory.subsidy_id самой категории, к которой она отнесена — закупка
    «чужой» субсидии (или вовсе без subsidy_id) в чужое дерево не попадает,
    даже если запрошено сразу несколько subsidy_ids одним батчем.

    exclude_planned_item_linked=True — исключить позиции с
    PurchaseItem.feo_planned_item_id IS NOT NULL (они уже расходуют план
    конкретной FeoPlannedItem — Ур.5 — и не должны задваиваться с планом
    самого листа; используется _calculate_feo_planned_tree_bulk).
    """
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    from app.routers.purchase_budget import PLANNED_STATUSES  # local: avoid router import cycle

    # Задача владельца «план ≠ факт» (шаг B, сессия 2026-08-06): суммируем СНИМОК
    # плана (planned_total/planned_quantity), а не мутирующую total_price/quantity —
    # иначе правка цены ТЗ по итогам закупки (единственный оставшийся путь — заявка)
    # двигала бы план у НЕпривязанных к FeoPlannedItem позиций. Снимок заполняется
    # Шагом 1 (purchases.py/wishes.py) и заморожен с момента ухода из «План закупок»
    # (см. patch_purchase_item); COALESCE — на случай строк без снимка (создано до
    # миграции j1k2l3m4n5o6 и ещё не сохранялось повторно).
    amount_expr = func.coalesce(PurchaseItem.planned_total, PurchaseItem.total_price)
    qty_expr = func.coalesce(PurchaseItem.planned_quantity, PurchaseItem.quantity)
    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    stmt = (
        select(
            cat_col.label("cat_id"),
            PurchaseItem.over_plan,
            func.coalesce(func.sum(amount_expr), 0).label("amount"),
            func.coalesce(func.sum(qty_expr), 0).label("qty"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(FeoCategory, FeoCategory.id == cat_col)
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        .where(Purchase.subsidy_id == FeoCategory.subsidy_id)
        .group_by(cat_col, PurchaseItem.over_plan)
    )
    if exclude_planned_item_linked:
        stmt = stmt.where(PurchaseItem.feo_planned_item_id.is_(None))

    rows = (await db.execute(stmt)).all()
    for r in rows:
        d = result.setdefault(r.cat_id, {
            "consumed": 0.0, "consumed_quantity": 0.0,
            "over": 0.0, "over_quantity": 0.0,
        })
        if r.over_plan:
            d["over"] += float(r.amount)
            d["over_quantity"] += float(r.qty)
        else:
            d["consumed"] += float(r.amount)
            d["consumed_quantity"] += float(r.qty)
    return result


async def ordered_consumption_by_category(
    db: AsyncSession,
    subsidy_ids: list[int],
    exclude_planned_item_linked: bool = False,
) -> dict[int, dict]:
    """{feo_category_id: {ordered, ordered_quantity}} — ФАКТИЧЕСКАЯ сумма и
    количество позиций закупок в статусах «Заказано»/«Поставлено»/«Оплачено»
    (ORDERED_STATUSES), отнесённых к конечному элементу дерева ФЭО (COALESCE
    (PurchaseItem.feo_category_id, Purchase.feo_category_id)), по правилам
    purchase_item_fact_amount (единая формула факта, см. её docstring).

    over_plan=true позиции исключены — их сумма прибавляется поверх плана
    безусловно (см. plan_consumption_by_category.over) и в замещение плана
    (ordered_qty ≥ planned_quantity) не участвует.

    Используется compute_feo_plan_tree — новая формула «плановой суммы»
    (сессия 2026-08-05, задача владельца): план = ordered_sum, если
    ordered_qty ≥ planned_quantity элемента, иначе plan_manual (пока не
    набрано всё плановое количество, бюджет зарезервирован целиком).

    exclude_planned_item_linked — см. plan_consumption_by_category, тот же
    смысл: позиции, привязанные к конкретной FeoPlannedItem (Ур.5), не
    задваивают план листа целиком.

    Изоляция субсидий — как в plan_consumption_by_category (Purchase.
    subsidy_id == FeoCategory.subsidy_id категории, к которой отнесена
    позиция).
    """
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    stmt = (
        select(PurchaseItem, Purchase, cat_col.label("cat_id"))
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(FeoCategory, FeoCategory.id == cat_col)
        .where(Purchase.status.in_(list(ORDERED_STATUSES)))
        .where(PurchaseItem.over_plan.is_(False))
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        .where(Purchase.subsidy_id == FeoCategory.subsidy_id)
    )
    if exclude_planned_item_linked:
        stmt = stmt.where(PurchaseItem.feo_planned_item_id.is_(None))

    rows = (await db.execute(stmt)).all()
    if not rows:
        return result

    # Пропорциональное распределение сумм уровня закупки (contract_price/
    # acceptance_doc_amount) между ВСЕМИ позициями закупки — как в /comparison,
    # считаем по всем позициям закупки, не только вошедшим в выборку.
    purchase_ids = {r.Purchase.id for r in rows}
    purchase_totals = await _purchase_item_totals(db, purchase_ids)
    # Приоритет №1 формулы факта (см. purchase_item_fact_amount) — ContractItem.total
    # по source_item_id, предзапрошено одним батчем на все позиции выборки.
    contract_totals = await _contract_item_totals(db, (r.PurchaseItem.id for r in rows))

    for r in rows:
        pi = r.PurchaseItem
        p = r.Purchase
        items_count, items_sum = purchase_totals.get(p.id, (1, Decimal(str(pi.total_price or 0))))
        item_total = Decimal(str(pi.total_price or 0))
        if items_count > 1 and items_sum > 0:
            ratio = item_total / items_sum
        elif items_count > 1:
            ratio = Decimal(1) / Decimal(items_count)
        else:
            ratio = Decimal(1)
        fact_amount, _allocated = purchase_item_fact_amount(
            pi, p, ratio, items_count, contract_item_total=contract_totals.get(pi.id)
        )
        if fact_amount is None:
            continue
        d = result.setdefault(r.cat_id, {"ordered": 0.0, "ordered_quantity": 0.0})
        d["ordered"] += float(fact_amount)
        d["ordered_quantity"] += float(pi.quantity or 0)
    return result


async def fact_consumption_by_category(
    db: AsyncSession,
    subsidy_ids: list[int],
) -> dict[int, dict]:
    """{feo_category_id: {fact, fact_quantity}} — задача владельца «план ≠ факт»
    (шаг A.2, сессия 2026-08-06): ФАКТ узла дерева ФЭО = Σ фактической суммы/
    количества позиций закупок в FACT_ELIGIBLE_STATUSES (work_in_progress и
    дальше — см. purchase_item_fact_amount), по правилам той же единой формулы.

    Отличие от ordered_consumption_by_category — ДВА:
      1. Порог статуса ниже (с «Ведётся работа», не с «Заказано») — превентивный
         контроль превышения должен видеть цену по итогам КП/торгов ДО подписания
         договора (см. assert_no_unapproved_excess).
      2. Позиции, привязанные к FeoPlannedItem (feo_planned_item_id IS NOT NULL),
         НЕ исключаются (в отличие от exclude_planned_item_linked=True, которым
         compute_feo_plan_tree вызывает ordered/plan_consumption) — иначе именно
         привязанные позиции (обычный сценарий: заявка → план → закупка) никогда
         не показали бы факт, хотя это и есть основной случай владельца (Great
         Wall POER, эталонный сценарий).

    over_plan=true позиции исключены — они не участвуют в сравнении факт/план
    (их расход уже безусловно учтён отдельно в excess_over_feo/over, см.
    plan_consumption_by_category.over и compute_feo_plan_tree).

    Изоляция субсидий — как в plan_consumption_by_category/ordered_consumption_by_category.
    """
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    stmt = (
        select(PurchaseItem, Purchase, cat_col.label("cat_id"))
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(FeoCategory, FeoCategory.id == cat_col)
        .where(Purchase.status.in_(list(FACT_ELIGIBLE_STATUSES)))
        .where(PurchaseItem.over_plan.is_(False))
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        .where(Purchase.subsidy_id == FeoCategory.subsidy_id)
    )

    rows = (await db.execute(stmt)).all()
    if not rows:
        return result

    purchase_ids = {r.Purchase.id for r in rows}
    purchase_totals = await _purchase_item_totals(db, purchase_ids)
    contract_totals = await _contract_item_totals(db, (r.PurchaseItem.id for r in rows))

    for r in rows:
        pi = r.PurchaseItem
        p = r.Purchase
        items_count, items_sum = purchase_totals.get(p.id, (1, Decimal(str(pi.total_price or 0))))
        item_total = Decimal(str(pi.total_price or 0))
        if items_count > 1 and items_sum > 0:
            ratio = item_total / items_sum
        elif items_count > 1:
            ratio = Decimal(1) / Decimal(items_count)
        else:
            ratio = Decimal(1)
        fact_amount, _allocated = purchase_item_fact_amount(
            pi, p, ratio, items_count, contract_item_total=contract_totals.get(pi.id)
        )
        if fact_amount is None:
            continue
        d = result.setdefault(r.cat_id, {"fact": 0.0, "fact_quantity": 0.0})
        d["fact"] += float(fact_amount)
        d["fact_quantity"] += float(pi.quantity or 0)
    return result


async def planned_item_consumption(
    db: AsyncSession,
    item_ids: list[int],
    exclude_purchase_id: Optional[int] = None,
    exclude_wish_id: Optional[int] = None,
) -> dict[int, dict]:
    """{feo_planned_item_id: {used, used_qty, wish_used, linked_purchase_ids}}

    Расход конкретной плановой позиции (FeoPlannedItem, Ур.5) через
    PurchaseItem.feo_planned_item_id / WishItem.feo_planned_item_id. Общая
    часть GET /api/feo-planned-items/residuals и
    GET /api/feo-categories/plan-positions — чтобы оба эндпоинта считали
    расход плановой позиции одинаково и не расходились.

    used/used_qty — SUM по PurchaseItem в PLANNED_STATUSES, привязанным к
    item_ids через feo_planned_item_id.
    wish_used — SUM WishItem.total_price ещё не сконвертированных заявок
    (draft/submitted/approved, purchase_id IS NULL), уже «бронирующих» план.
    linked_purchase_ids — уникальные id закупок, чьи позиции привязаны к
    плановой позиции (тоже только PLANNED_STATUSES).
    """
    result: dict[int, dict] = {
        iid: {"used": 0.0, "used_qty": 0.0, "wish_used": 0.0, "linked_purchase_ids": []}
        for iid in item_ids
    }
    if not item_ids:
        return result

    from app.routers.purchase_budget import PLANNED_STATUSES  # local: avoid router import cycle

    used_q = (
        select(
            PurchaseItem.feo_planned_item_id,
            func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
            func.coalesce(func.sum(PurchaseItem.quantity), 0).label("used_qty"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
    )
    if exclude_purchase_id is not None:
        used_q = used_q.where(PurchaseItem.purchase_id != exclude_purchase_id)
    if exclude_wish_id is not None:
        used_q = used_q.where(sqlor(Purchase.wish_id != exclude_wish_id, Purchase.wish_id.is_(None)))
    used_q = used_q.group_by(PurchaseItem.feo_planned_item_id)
    for r in (await db.execute(used_q)).all():
        result[r.feo_planned_item_id]["used"] = float(r.used)
        result[r.feo_planned_item_id]["used_qty"] = float(r.used_qty)

    wish_used_q = (
        select(
            WishItem.feo_planned_item_id,
            func.coalesce(func.sum(WishItem.total_price), 0).label("wish_used"),
        )
        .join(Wish, WishItem.wish_id == Wish.id)
        .where(WishItem.feo_planned_item_id.in_(item_ids))
        .where(Wish.status.in_(("draft", "submitted", "approved")))
        .where(Wish.purchase_id.is_(None))
    )
    if exclude_wish_id is not None:
        wish_used_q = wish_used_q.where(Wish.id != exclude_wish_id)
    wish_used_q = wish_used_q.group_by(WishItem.feo_planned_item_id)
    for r in (await db.execute(wish_used_q)).all():
        result[r.feo_planned_item_id]["wish_used"] = float(r.wish_used)

    links_q = (
        select(PurchaseItem.feo_planned_item_id, PurchaseItem.purchase_id)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
    )
    if exclude_purchase_id is not None:
        links_q = links_q.where(PurchaseItem.purchase_id != exclude_purchase_id)
    if exclude_wish_id is not None:
        links_q = links_q.where(sqlor(Purchase.wish_id != exclude_wish_id, Purchase.wish_id.is_(None)))
    for lr in (await db.execute(links_q)).all():
        lst = result[lr.feo_planned_item_id]["linked_purchase_ids"]
        if lr.purchase_id not in lst:
            lst.append(lr.purchase_id)

    return result


async def compute_feo_plan_tree(
    db: AsyncSession, subsidy_ids: list[int]
) -> dict[int, dict]:
    """Рекурсивная формула «плановой суммы» дерева ФЭО — единый источник для
    _calculate_feo_planned_tree_bulk (subsidies.py, KPI «Запланировано»/«Свободно»
    на дашборде, в списке субсидий и в панели субсидии), _create_plan_graph_version
    (purchases.py, снапшот версии плана закупок), GET /api/feo-categories/plan-positions
    и GET /api/feo-categories/planned-purchase-totals.

    ФОРМУЛА v2 (сессия 2026-08-05, задача владельца «заказ замещает план, пока не
    набрано количество — план не трогаем»). Раньше было display = MAX(plan_manual,
    consumed) + over — эконом на частичном заказе не высвобождался, пока не заказано
    ВСЁ количество целиком. Теперь — явная замена, а не MAX:

    Для каждой категории cat_id (и листа, и группы — не только листьев) считается:
      plan_manual — «сколько сами запланировали»:
        лист:  planned_quantity × planned_amount (planned_amount — цена за
               единицу); если произведение = 0, а активные FeoPlannedItem (Ур.5)
               есть — fallback на Σ FeoPlannedItem.amount (план введён по
               позициям, а не по листу целиком);
        группа: Σ plan_manual прямых детей. Собственные planned_quantity/amount
                группы НЕ учитываются — так же, как feoPlannedTotalFor во
                фронте, иначе формулы разойдутся (см. ниже — по той же причине
                «собственная» часть группы всегда даёт 0 в plan/plan_manual).
      ordered / ordered_quantity — Σ фактической суммы/количества позиций в
        статусах «Заказано»/«Поставлено»/«Оплачено» (ORDERED_STATUSES,
        см. ordered_consumption_by_category), БЕЗ over_plan=true и БЕЗ
        привязанных к FeoPlannedItem (Ур.5) — этого узла + рекурсивно всех
        потомков. Это то самое «реально заказанное количество/сумма», которое
        решает, замещать план или нет.
      over — Σ сумм позиций с over_plan=true по ВСЕМ PLANNED_STATUSES (как и
        раньше — расход «сверх плана», прибавляется безусловно поверх, не
        участвует в замещении), этого узла + рекурсивно всех потомков.
      plan — собственно «план замещается заказом»:
        лист:   ordered, ЕСЛИ planned_quantity > 0 И ordered_quantity ≥
                planned_quantity (количество набрано целиком) — план
                становится фактической суммой заказа, экономия/переплата
                высвобождается; ИНАЧЕ (заказано частично или количество не
                задано) — plan_manual (весь план резервируется, даже если
                частично уже заказано дешевле/дороже).
        группа: Σ plan прямых детей + «собственный» plan узла (та же формула
                относительно planned_quantity/ordered_quantity САМОЙ группы —
                но т.к. planned_quantity группы не учитывается (см. выше),
                собственная часть группы всегда равна 0, own-позиции группы
                в план не попадают — они и раньше терялись в MAX, если не
                превышали план детей; см. проверенный кейс с группой
                «Внедорожник повышенной проходимости»).
      display — «плановая сумма» для UI/KPI = plan + over.
      residual — plan − ordered (может уйти в минус — «перерасход» в UI).
      ordered_qty / ordered_sum — алиасы ordered_quantity/ordered (те же значения,
        под именами, ожидаемыми GET /api/feo-categories/plan-tree, сессия 2026-08-05
        задача «формула только на бэкенде» — фронт больше не пересчитывает план сам,
        читает готовые числа с бэкенда и не должен путать имена полей).
      over_quantity — Σ количества позиций с over_plan=true (аналогично over, но
        в штуках/ед.изм.), этого узла + рекурсивно всех потомков.
      consumed / consumed_quantity — Σ суммы/количества ВСЕХ позиций ВО ВСЕХ
        PLANNED_STATUSES (включая ещё не заказанные — plan_schedule/
        work_in_progress/contracted), БЕЗ over_plan=true и БЕЗ привязанных к
        FeoPlannedItem (см. plan_consumption_by_category.consumed) — этого узла +
        рекурсивно всех потомков. Шире, чем ordered/ordered_quantity (которые
        считают только реально РАЗМЕЩЁННЫЕ закупки, ORDERED_STATUSES) — «сколько
        вообще заявлено», а не «сколько реально заказано».
      qty_plan / display_quantity — то же замещение «заказ вместо плана», что и
        plan/display, но для количества (аналог для GET /api/feo-categories/
        plan-tree и «Планового количества» в SubsidiesView.vue): лист — ordered_qty,
        ЕСЛИ planned_quantity > 0 И ordered_qty ≥ planned_quantity, иначе
        planned_quantity; группа — Σ qty_plan прямых детей (собственное
        planned_quantity группы не учитывается — та же причина, что и у plan).
        display_quantity = qty_plan + over_quantity.
      forecast / forecast_over — прогнозное предупреждение (не блокирует,
        только для UI): avg_ordered_price = ordered / ordered_quantity (если
        ordered_quantity > 0); forecast = ordered + оставшееся_количество ×
        avg_ordered_price; forecast_over = max(0, forecast − plan_manual).
        Для узлов без заказов или без planned_quantity forecast = plan_manual,
        forecast_over = 0 (прогнозировать не на чем). Для групп — только
        накопление forecast_over детей (rollup-индикатор «где-то в подветке
        цена выше плановой»), их собственная часть не считается по той же
        причине, что и plan.

    К каждому узлу также приложены subsidy_id/parent_id, чтобы вызывающий код мог
    просуммировать корневые узлы (parent_id IS NULL) для тотала субсидии без
    повторного запроса к FeoCategory.

    Изоляция субсидий обеспечивается plan_consumption_by_category/
    ordered_consumption_by_category (см. их docstring) — результат не зависит
    от состава батча subsidy_ids.
    """
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result
    from app.models.feo_planned_item import FeoPlannedItem

    cat_q = select(
        FeoCategory.id, FeoCategory.subsidy_id, FeoCategory.parent_id,
        FeoCategory.planned_quantity, FeoCategory.planned_amount, FeoCategory.budget,
    ).where(FeoCategory.subsidy_id.in_(subsidy_ids))
    cat_rows = (await db.execute(cat_q)).all()
    if not cat_rows:
        return result

    by_id = {r.id: r for r in cat_rows}
    children_map: dict[int, list[int]] = {}
    has_children: set[int] = set()
    for r in cat_rows:
        if r.parent_id is not None and r.parent_id in by_id:
            has_children.add(r.parent_id)
            children_map.setdefault(r.parent_id, []).append(r.id)

    leaf_ids = [r.id for r in cat_rows if r.id not in has_children]

    # Fallback-сумма Σ FeoPlannedItem.amount активных позиций Ур.5 per лист — нужна,
    # когда planned_quantity/planned_amount листа не заполнены, а план введён
    # позициями (импорт Excel).
    leaf_item_amt: dict[int, float] = {}
    if leaf_ids:
        fpi_q = (
            select(
                FeoPlannedItem.feo_category_id,
                func.coalesce(func.sum(FeoPlannedItem.amount), 0).label("amt"),
            )
            .where(FeoPlannedItem.feo_category_id.in_(leaf_ids))
            .where(FeoPlannedItem.is_active.is_(True))
            .group_by(FeoPlannedItem.feo_category_id)
        )
        for r in (await db.execute(fpi_q)).all():
            leaf_item_amt[r.feo_category_id] = float(r.amt)

    over_consumption = await plan_consumption_by_category(db, subsidy_ids, exclude_planned_item_linked=True)
    ordered_consumption = await ordered_consumption_by_category(db, subsidy_ids, exclude_planned_item_linked=True)
    fact_consumption = await fact_consumption_by_category(db, subsidy_ids)

    # Согласование превышения плана над финансированием узла (feo_categories.budget) —
    # задача владельца «должны быть заблокированы действия, пока план закупок не
    # загонять обратно в размеры ФЭО» + «согласование цепочкой». Берём ПОСЛЕДНИЙ
    # (по created_at) запрос plan_excess_approvals на каждый узел — если approved,
    # превышение считается легализованным и полностью входит в display; если
    # pending/rejected/отсутствует — превышение НЕ входит в display (остаётся
    # plan_manual), но видно отдельно в excess_amount/excess_pending для UI-бейджа
    # (см. GET /api/feo-categories/plan-tree, frontend SubsidiesView.vue).
    from app.models.plan_excess_approval import PlanExcessApproval
    latest_approval_by_cat: dict[int, PlanExcessApproval] = {}
    if by_id:
        appr_rows = (await db.execute(
            select(PlanExcessApproval)
            .where(PlanExcessApproval.feo_category_id.in_(list(by_id.keys())))
            .order_by(PlanExcessApproval.feo_category_id, PlanExcessApproval.created_at.desc())
        )).scalars().all()
        for a in appr_rows:
            if a.feo_category_id not in latest_approval_by_cat:
                latest_approval_by_cat[a.feo_category_id] = a

    def _own_plan_and_forecast(qty: float, amt: float, plan_manual: float, ordered: float, ordered_qty: float):
        """Формула замещения плана заказом для ОДНОГО узла (без учёта детей) —
        общая для листа и «собственной» части группы. qty/amt — planned_quantity/
        planned_amount именно этого узла (для группы — всегда 0, см. вызывающий код)."""
        plan = ordered if (qty > 0 and ordered_qty >= qty) else plan_manual
        if ordered_qty > 0:
            avg_price = ordered / ordered_qty
            remaining_qty = max(0.0, qty - ordered_qty) if qty > 0 else 0.0
            forecast = ordered + remaining_qty * avg_price
            forecast_over = max(0.0, forecast - plan_manual)
        else:
            forecast = plan_manual
            forecast_over = 0.0
        return plan, forecast, forecast_over

    def _visit(cat_id: int) -> dict:
        cached = result.get(cat_id)
        if cached is not None:
            return cached
        r = by_id[cat_id]
        over_cons = over_consumption.get(cat_id) or {}
        own_over = over_cons.get("over", 0.0)
        own_over_qty = over_cons.get("over_quantity", 0.0)
        own_consumed = over_cons.get("consumed", 0.0)
        own_consumed_qty = over_cons.get("consumed_quantity", 0.0)
        ord_cons = ordered_consumption.get(cat_id) or {}
        own_ordered = ord_cons.get("ordered", 0.0)
        own_ordered_qty = ord_cons.get("ordered_quantity", 0.0)
        fact_cons = fact_consumption.get(cat_id) or {}
        own_fact = fact_cons.get("fact", 0.0)
        own_fact_qty = fact_cons.get("fact_quantity", 0.0)

        kids = children_map.get(cat_id, [])
        if not kids:
            qty = float(r.planned_quantity) if r.planned_quantity is not None else 0.0
            amt = float(r.planned_amount) if r.planned_amount is not None else 0.0
            plan_manual = (qty * amt) if (qty > 0 and amt > 0) else 0.0
            if plan_manual == 0.0:
                plan_manual = leaf_item_amt.get(cat_id, 0.0)
            ordered = own_ordered
            ordered_qty = own_ordered_qty
            over = own_over
            over_qty = own_over_qty
            consumed = own_consumed
            consumed_qty = own_consumed_qty
            fact = own_fact
            fact_qty = own_fact_qty
            plan, forecast, forecast_over = _own_plan_and_forecast(qty, amt, plan_manual, ordered, ordered_qty)
            # qty_plan — тот же принцип замещения, что и plan (money), но для
            # количества: заказанное количество замещает плановое, когда оно набрано
            # полностью, иначе показывается всё плановое количество листа.
            qty_plan = ordered_qty if (qty > 0 and ordered_qty >= qty) else qty
        else:
            child_nodes = [_visit(c) for c in kids]
            children_plan = sum(c["plan"] for c in child_nodes)
            children_plan_manual = sum(c["plan_manual"] for c in child_nodes)
            children_ordered = sum(c["ordered"] for c in child_nodes)
            children_ordered_qty = sum(c["ordered_quantity"] for c in child_nodes)
            children_over = sum(c["over"] for c in child_nodes)
            children_over_qty = sum(c["over_quantity"] for c in child_nodes)
            children_consumed = sum(c["consumed"] for c in child_nodes)
            children_consumed_qty = sum(c["consumed_quantity"] for c in child_nodes)
            children_forecast_over = sum(c["forecast_over"] for c in child_nodes)
            children_fact = sum(c["fact"] for c in child_nodes)
            children_fact_qty = sum(c["fact_quantity"] for c in child_nodes)

            # Собственные planned_quantity/amount группы НЕ учитываются (см. docstring) —
            # own-часть формулы всегда получает qty=0, поэтому own_plan всегда
            # схлопывается к own_plan_manual=0 (замещать нечего, цели нет).
            own_plan, _own_forecast, _own_forecast_over = _own_plan_and_forecast(
                0.0, 0.0, 0.0, own_ordered, own_ordered_qty
            )

            plan_manual = children_plan_manual
            ordered = own_ordered + children_ordered
            ordered_qty = own_ordered_qty + children_ordered_qty
            over = own_over + children_over
            over_qty = own_over_qty + children_over_qty
            consumed = own_consumed + children_consumed
            consumed_qty = own_consumed_qty + children_consumed_qty
            fact = own_fact + children_fact
            fact_qty = own_fact_qty + children_fact_qty
            plan = own_plan + children_plan
            forecast_over = children_forecast_over
            forecast = plan_manual + forecast_over
            # Собственное plan_quantity группы тоже НЕ учитывается — та же причина,
            # что и own_plan выше (own_qty_plan всегда 0, qty=0 → условие ложно).
            children_qty_plan = sum(c["qty_plan"] for c in child_nodes)
            qty_plan = children_qty_plan

        # Согласование превышения (см. комментарий у latest_approval_by_cat выше):
        # full_display — «настоящая» плановая сумма узла (как считалось раньше,
        # ДО задачи владельца «блокировать пока не согласовано превышение»).
        # Если она превышает финансирование по ФЭО (budget) и превышение НЕ
        # согласовано — display откатывается к plan_manual (превышение не входит
        # в план, пока не согласовано или не убрано обратно в рамки).
        budget = float(r.budget) if r.budget is not None else None
        full_display = plan + over
        excess_amount = 0.0
        excess_pending = False
        excess_approved = False
        display = full_display
        appr = latest_approval_by_cat.get(cat_id)
        if budget is not None and full_display - budget > 0.005:
            excess_amount = full_display - budget
            if appr is not None and appr.status == "approved":
                excess_approved = True
                display = full_display
            else:
                display = plan_manual
                excess_pending = bool(appr is not None and appr.status == "pending")

        # Задача владельца «план ≠ факт» (шаг C, сессия 2026-08-06): ВТОРОЕ,
        # независимое превышение — «факт дороже плана» (итог закупки/КП больше,
        # чем было запланировано), а НЕ «план дороже финансирования ФЭО»
        # (excess_amount/excess_over_feo — старая, НЕ изменённая семантика, см.
        # выше). excess_amount оставлен как есть для обратной совместимости
        # существующих потребителей; excess_over_feo — то же число под понятным
        # именем. НЕ влияет на display/full_display — это отдельный сигнал для
        # гейта (assert_no_unapproved_excess) и панелей факт/план, а не для
        # KPI «Запланировано».
        excess_over_feo = excess_amount
        excess_fact_over_plan = (fact - plan) if (fact - plan) > 0.005 else 0.0
        # Согласование превышения факта над планом — та же PlanExcessApproval-запись
        # на категорию (единый механизм согласования, задача владельца «согласование
        # существующим механизмом»): approved снимает блокировку для ОБОИХ видов
        # превышения одновременно (см. assert_no_unapproved_excess/plan_excess.py).
        excess_fact_approved = bool(excess_fact_over_plan > 0.005 and appr is not None and appr.status == "approved")
        excess_fact_pending = bool(excess_fact_over_plan > 0.005 and appr is not None and appr.status == "pending")

        node = {
            "subsidy_id": r.subsidy_id,
            "parent_id": r.parent_id,
            "plan_manual": plan_manual,
            "ordered": ordered,
            "ordered_quantity": ordered_qty,
            "ordered_qty": ordered_qty,
            "ordered_sum": ordered,
            "over": over,
            "over_quantity": over_qty,
            "consumed": consumed,
            "consumed_quantity": consumed_qty,
            "fact": fact,
            "fact_quantity": fact_qty,
            "plan": plan,
            "budget": budget,
            "display": display,
            "excess_amount": excess_amount,
            "excess_pending": excess_pending,
            "excess_approved": excess_approved,
            "excess_over_feo": excess_over_feo,
            "excess_fact_over_plan": excess_fact_over_plan,
            "excess_fact_approved": excess_fact_approved,
            "excess_fact_pending": excess_fact_pending,
            "residual": plan - ordered,
            "forecast": forecast,
            "forecast_over": forecast_over,
            "qty_plan": qty_plan,
            "display_quantity": qty_plan + over_qty,
        }
        result[cat_id] = node
        return node

    for cid in by_id:
        _visit(cid)
    return result


async def assert_no_unapproved_excess(
    db: AsyncSession, feo_category_id: int, adding_amount: Decimal = Decimal("0")
) -> None:
    """Бросает HTTPException 409, если узел ФЭО feo_category_id или любой его
    ПРЕДОК имеет несогласованное превышение — ЛИБО плана над финансированием ФЭО
    (excess_over_feo/excess_amount > 0 и НЕ excess_approved), ЛИБО факта над
    планом (excess_fact_over_plan > 0 и НЕ excess_fact_approved — задача
    владельца «план ≠ факт», шаг C, сессия 2026-08-06). См. compute_feo_plan_tree
    и app.models.plan_excess_approval.

    Требование владельца (2026-08-05): «Если где-то превысил план ФЭО, значит
    где-то надо снимать — должны быть заблокированы действия, пока план закупок
    не загонять обратно в размеры ФЭО». Требование владельца (2026-08-06,
    превентивность): контроль факт-над-планом включается уже на «Ведётся
    работа» (см. FACT_PRICED_STATUSES) — переход закупки в «Договор» и
    увеличение договорных позиций блокируются ДО подписания, пока превышение
    итога закупки над планом не согласовано.

    Вызывается ПЕРЕД действиями, УВЕЛИЧИВАЮЩИМИ план (создание закупки,
    увеличение суммы/смена категории ФЭО при PUT, согласование заявки →
    создание закупок) и ПЕРЕД действиями, УВЕЛИЧИВАЮЩИМИ факт сверх плана
    (переход статуса закупки work_in_progress → contracted, сохранение/
    изменение договорных позиций) — см. вызывающий код в app.routers.purchases /
    app.routers.wishes / app.routers.contract_items.

    НЕ вызывается для переходов статусов вперёд у уже существующих закупок
    (ordered → delivered → paid), уменьшений сумм, удаления позиций, отката
    заявок — это путь ВОЗВРАТА в рамки плана, его блокировать нельзя.

    adding_amount — необязательная сумма добавляемого действия, используется
    ТОЛЬКО для текста отказа (сколько ещё пытаются добавить сверху уже
    несогласованного превышения); на решение блокировать/не блокировать не
    влияет — блокирует сам факт СУЩЕСТВУЮЩЕГО несогласованного превышения на
    узле или предке (см. сценарий владельца: первая закупка, создавшая
    превышение, не блокируется — блокируется каждая СЛЕДУЮЩАЯ, пока
    превышение не согласовано или не убрано).
    """
    from fastapi import HTTPException

    cat = await db.get(FeoCategory, feo_category_id)
    if cat is None:
        return

    tree = await compute_feo_plan_tree(db, [cat.subsidy_id])
    if not tree or feo_category_id not in tree:
        return

    # Цепочка «узел → предки» через parent_id (снизу вверх)
    chain_ids: list[int] = []
    cur_id: Optional[int] = feo_category_id
    seen: set[int] = set()
    while cur_id is not None and cur_id not in seen and cur_id in tree:
        seen.add(cur_id)
        chain_ids.append(cur_id)
        cur_id = tree[cur_id]["parent_id"]

    for cid in chain_ids:
        node = tree[cid]
        extra = (
            f" Запрашиваемое действие добавляет ещё {Decimal(str(adding_amount)):,.2f} ₽ поверх этого."
            if adding_amount else ""
        )

        excess = node.get("excess_amount") or 0.0
        if excess > 0.005 and not node.get("excess_approved"):
            cat_row = await db.get(FeoCategory, cid)
            name = cat_row.name if cat_row else f"#{cid}"
            budget_d = Decimal(str(node.get("budget") or 0.0))
            full_plan_d = Decimal(str(node["plan"] + node["over"]))  # текущая плановая сумма (до сжатия по бюджету)
            excess_d = Decimal(str(excess))
            raise HTTPException(
                409,
                f"Превышение плана по категории ФЭО «{name}»: финансирование по ФЭО "
                f"{budget_d:,.2f} ₽, текущая плановая сумма {full_plan_d:,.2f} ₽, превышение "
                f"{excess_d:,.2f} ₽.{extra} Снимите позиции на {excess_d:,.2f} ₽ или согласуйте "
                f"превышение (запрос согласования превышения плана ФЭО по категории «{name}»)."
            )

        excess_fact = node.get("excess_fact_over_plan") or 0.0
        if excess_fact > 0.005 and not node.get("excess_fact_approved"):
            cat_row = await db.get(FeoCategory, cid)
            name = cat_row.name if cat_row else f"#{cid}"
            plan_d = Decimal(str(node.get("plan") or 0.0))
            fact_d = Decimal(str(node.get("fact") or 0.0))
            excess_fact_d = Decimal(str(excess_fact))
            raise HTTPException(
                409,
                f"Итог закупки по категории ФЭО «{name}» превышает план: план "
                f"{plan_d:,.2f} ₽, факт (по договору/КП) {fact_d:,.2f} ₽, превышение "
                f"{excess_fact_d:,.2f} ₽.{extra} Переход в «Договор» и увеличение договорных "
                f"позиций заблокированы, пока превышение не согласовано (запрос согласования "
                f"превышения плана по категории «{name}») или сумма договора не снижена до плана."
            )


async def feo_plan_subsidy_totals(
    db: AsyncSession, subsidy_ids: list[int]
) -> dict[int, float]:
    """Σ display корневых узлов (parent_id IS NULL) дерева ФЭО per субсидия —
    единственное число KPI «Запланировано» (used by _calculate_feo_planned_tree_bulk
    в subsidies.py и total_plan_combined в _create_plan_graph_version в
    purchases.py). Тонкая обёртка над compute_feo_plan_tree — см. её docstring
    за формулой.
    """
    result = {sid: 0.0 for sid in subsidy_ids}
    if not subsidy_ids:
        return result
    tree = await compute_feo_plan_tree(db, subsidy_ids)
    for node in tree.values():
        if node["parent_id"] is None:
            result[node["subsidy_id"]] = result.get(node["subsidy_id"], 0.0) + node["display"]
    return result


def build_category_path(cat, cat_by_id: dict) -> str:
    """Путь категории «Направление › Подкатегория › Лист» (сверху вниз).

    cat_by_id — {id: FeoCategory} для всех категорий той же субсидии
    (нужен для подъёма по parent_id без доп. запросов к БД).
    """
    if cat is None:
        return ""
    names = [cat.name]
    cur = cat
    while cur.parent_id is not None and cur.parent_id in cat_by_id:
        cur = cat_by_id[cur.parent_id]
        names.append(cur.name)
    return " › ".join(reversed(names))


def build_ancestor_ids(cat, cat_by_id: dict) -> list:
    """id всех предков категории, от корня до непосредственного родителя (сверху вниз).

    Не включает саму `cat`. cat_by_id — {id: FeoCategory} той же субсидии (см.
    build_category_path). Нужен фронту (GET /feo-categories/plan-positions), чтобы
    находить плановые позиции вложенных конечных категорий по id родителя, выбранного
    в дереве, БЕЗ обхода обрезанного фронтового дерева (frontend/useFeoLeaves
    filterFundedNodes вырезает конечные узлы без собственного budget — см. баг «В этой
    категории нет плановых позиций», сессия 2026-08-05).
    """
    if cat is None:
        return []
    ids = []
    cur = cat
    while cur.parent_id is not None and cur.parent_id in cat_by_id:
        cur = cat_by_id[cur.parent_id]
        ids.append(cur.id)
    return list(reversed(ids))
