"""feo_plan_payments.py — «оплачено» (по отметке / подтверждено выпиской) дерева ФЭО.

Решение владельца (02.10.2026): «Оплату может отметить сам закупщик — поставил
платёж, перевёл закупку в Оплачено. Нужна отдельная величина — оплата
подтверждена выпиской: когда загружены файлы выписки, платёж в них нашёлся и
сопоставился. Только тогда сумма подтверждённая».

ПРАВИЛО №6 — переиспользует уже существующие поля закупки, НЕ считает новую
формулу: Purchase.payment_amount (подтверждено выпиской, Payment.confirmed_
by_statement=True) и Purchase.payment_amount_declared (ручная отметка без
подтверждения) — обе колонки пишет app.services.purchase_payments::
recompute_purchase_payments (тот файл в этой сессии не трогается — правит
параллельный агент).

Фильтрация строк (ПРАВИЛО №6 — та же выборка, что и у остальных сумм узла
дерева ФЭО) идентична plan_consumption_by_category (feo_plan_fact.py):
PLANNED_STATUSES, Purchase.stopped_at IS NULL, изоляция субсидий
(Purchase.subsidy_id == FeoCategory.subsidy_id категории, к которой отнесена
строка), тот же переключатель exclude_planned_item_linked.

Платёж живёт на закупке целиком, не на позиции — распределяется между
позициями ТОЙ ЖЕ пропорцией (доля total_price позиции в Σ total_price всех
позиций закупки), что purchase_item_fact_amount/_purchase_item_totals
(feo_plan_fact.py, не вторая копия формулы распределения), после чего
суммируется по категории так же, как amount_expr в plan_consumption_by_category.
"""
from decimal import Decimal

from sqlalchemy import func, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem


async def paid_consumption_rows(
    db: AsyncSession,
    subsidy_ids: list[int],
    exclude_planned_item_linked: bool = False,
) -> list[dict]:
    """[{"purchase_id","subsidy_id","cat_id","paid_marked","paid_confirmed"}]
    — ОДНО место, где платёж закупки распределяется на позиции/категории (см.
    докстринг модуля за формулой пропорции). ПРАВИЛО №6: `paid_consumption_
    by_category` (агрегат по категории, дерево ФЭО) и построчная расшифровка
    карточки «Остаток субсидии» (dashboard_metric_drill.py, metric_drill_rows.
    balance_drill) — ОБЕ читают ЭТИ строки, не считают ratio/paid_marked
    заново. Одна строка на (PurchaseItem, его категория) — несколько строк
    одной закупки суммируются её читателями по необходимости."""
    result: list[dict] = []
    if not subsidy_ids:
        return result

    from app.routers.purchase_budget import PLANNED_STATUSES  # local: avoid router import cycle
    from app.models.feo_planned_item import FeoPlannedItem
    from sqlalchemy.orm import aliased

    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    _fpi = aliased(FeoPlannedItem)

    # Знаменатель пропорции — Σ total_price ВСЕХ позиций закупки (не только тех,
    # что попали в этот батч subsidy_ids/категорий) — та же база, что у
    # _purchase_item_totals (feo_plan_fact.py), не отдельный расчёт.
    _purchase_totals_sq = (
        select(
            PurchaseItem.purchase_id.label("purchase_id"),
            func.coalesce(func.sum(PurchaseItem.total_price), 0).label("items_sum"),
            func.count(PurchaseItem.id).label("items_count"),
        )
        .group_by(PurchaseItem.purchase_id)
        .subquery()
    )

    stmt = (
        select(
            Purchase.id.label("purchase_id"),
            Purchase.subsidy_id.label("subsidy_id"),
            cat_col.label("cat_id"),
            PurchaseItem.total_price.label("item_total"),
            _purchase_totals_sq.c.items_sum,
            _purchase_totals_sq.c.items_count,
            Purchase.payment_amount,
            Purchase.payment_amount_declared,
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(FeoCategory, FeoCategory.id == cat_col)
        .outerjoin(_fpi, _fpi.id == PurchaseItem.feo_planned_item_id)
        .join(_purchase_totals_sq, _purchase_totals_sq.c.purchase_id == PurchaseItem.purchase_id)
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(Purchase.stopped_at.is_(None))
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        .where(Purchase.subsidy_id == FeoCategory.subsidy_id)
        .where(sqlor(Purchase.payment_amount.isnot(None), Purchase.payment_amount_declared.isnot(None)))
    )
    if exclude_planned_item_linked:
        stmt = stmt.where(
            sqlor(
                PurchaseItem.feo_planned_item_id.is_(None),
                _fpi.id.is_(None),
                _fpi.is_active.is_(False),
                _fpi.feo_category_id != cat_col,
            )
        )

    rows = (await db.execute(stmt)).all()
    for r in rows:
        items_sum = Decimal(str(r.items_sum or 0))
        item_total = Decimal(str(r.item_total or 0))
        items_count = int(r.items_count or 1)
        ratio = _item_ratio(item_total, items_sum, items_count)
        marked, confirmed = _item_payment_split(ratio, r.payment_amount, r.payment_amount_declared)

        result.append({
            "purchase_id": r.purchase_id,
            "subsidy_id": r.subsidy_id,
            "cat_id": r.cat_id,
            "paid_marked": float(marked),
            "paid_confirmed": float(confirmed),
        })
    return result


def _item_ratio(item_total: Decimal, items_sum: Decimal, items_count: int) -> Decimal:
    """Доля позиции в сумме её закупки — ЕДИНСТВЕННАЯ формула пропорции (см.
    докстринг модуля). Вынесена из paid_consumption_rows (была инлайн-кодом)
    ПРАВИЛО №6 — переиспользуется purchase_item_payment_amounts ниже
    (plan_item_stage.py, раскраска плана по стадии), сумма по категории не
    меняется (закреплено тестом test_plan_item_stage.py)."""
    if items_count > 1 and items_sum > 0:
        return item_total / items_sum
    if items_count > 1:
        return Decimal(1) / Decimal(items_count)
    return Decimal(1)


def _item_payment_split(ratio: Decimal, payment_amount, payment_amount_declared) -> tuple[Decimal, Decimal]:
    """Платёж закупки (payment_amount — подтверждено выпиской, +declared —
    ручная отметка), распределённый на позицию её `ratio`. Вынесена из
    paid_consumption_rows — та же формула, второй раз не считаем (ПРАВИЛО №6)."""
    marked = (Decimal(str(payment_amount or 0)) + Decimal(str(payment_amount_declared or 0))) * ratio
    confirmed = Decimal(str(payment_amount or 0)) * ratio
    return marked, confirmed


async def purchase_item_payment_amounts(db: AsyncSession, purchase_ids: list[int]) -> dict[int, dict]:
    """{purchase_item_id: {"paid_marked", "paid_confirmed", "item_total"}} — та же
    пропорция, что в paid_consumption_rows (_item_ratio/_item_payment_split,
    ПРАВИЛО №6, единственная формула распределения платежа закупки по позициям),
    но по произвольному списку purchase_id, без фильтра по категории/субсидии.
    Источник для app.services.plan_item_stage (раскраска плановых позиций дерева
    ФЭО по стадии оплаты) — второй расчёт ratio/marked/confirmed не заводится."""
    result: dict[int, dict] = {}
    if not purchase_ids:
        return result

    _purchase_totals_sq = (
        select(
            PurchaseItem.purchase_id.label("purchase_id"),
            func.coalesce(func.sum(PurchaseItem.total_price), 0).label("items_sum"),
            func.count(PurchaseItem.id).label("items_count"),
        )
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
        .group_by(PurchaseItem.purchase_id)
        .subquery()
    )
    stmt = (
        select(
            PurchaseItem.id.label("purchase_item_id"),
            PurchaseItem.total_price.label("item_total"),
            _purchase_totals_sq.c.items_sum,
            _purchase_totals_sq.c.items_count,
            Purchase.payment_amount,
            Purchase.payment_amount_declared,
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(_purchase_totals_sq, _purchase_totals_sq.c.purchase_id == PurchaseItem.purchase_id)
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
    )
    rows = (await db.execute(stmt)).all()
    for r in rows:
        items_sum = Decimal(str(r.items_sum or 0))
        item_total = Decimal(str(r.item_total or 0))
        items_count = int(r.items_count or 1)
        ratio = _item_ratio(item_total, items_sum, items_count)
        marked, confirmed = _item_payment_split(ratio, r.payment_amount, r.payment_amount_declared)
        result[r.purchase_item_id] = {
            "paid_marked": float(marked),
            "paid_confirmed": float(confirmed),
            "item_total": float(item_total),
        }
    return result


async def paid_consumption_by_category(
    db: AsyncSession,
    subsidy_ids: list[int],
    exclude_planned_item_linked: bool = False,
) -> dict[int, dict]:
    """{feo_category_id: {paid_marked, paid_confirmed}}

    paid_marked — Σ (payment_amount + payment_amount_declared) закупки,
    распределённая на позиции узла (= «Оплачено (по отметке)», включает
    неподтверждённые ручные отметки).
    paid_confirmed — Σ payment_amount (ТОЛЬКО подтверждённое выпиской),
    та же пропорция.

    exclude_planned_item_linked — та же семантика, что у
    plan_consumption_by_category: True исключает строки с валидной привязкой
    к активной FeoPlannedItem СВОЕЙ категории (уже учтены на уровне Ур.5,
    не задваиваются здесь) — вызывается с True там же, где и over_consumption
    (см. compute_feo_plan_tree._visit: own_consumed/own_over).

    ПРАВИЛО №6 — чистая агрегация paid_consumption_rows() по cat_id, raw
    ratio/payment-формула считается ТОЛЬКО там."""
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result
    rows = await paid_consumption_rows(db, subsidy_ids, exclude_planned_item_linked)
    for r in rows:
        d = result.setdefault(r["cat_id"], {"paid_marked": 0.0, "paid_confirmed": 0.0})
        d["paid_marked"] += r["paid_marked"]
        d["paid_confirmed"] += r["paid_confirmed"]
    return result
