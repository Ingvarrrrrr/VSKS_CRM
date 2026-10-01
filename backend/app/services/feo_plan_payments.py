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
    """
    result: dict[int, dict] = {}
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
        if items_count > 1 and items_sum > 0:
            ratio = item_total / items_sum
        elif items_count > 1:
            ratio = Decimal(1) / Decimal(items_count)
        else:
            ratio = Decimal(1)

        marked = Decimal(str(r.payment_amount or 0)) + Decimal(str(r.payment_amount_declared or 0))
        confirmed = Decimal(str(r.payment_amount or 0))

        d = result.setdefault(r.cat_id, {"paid_marked": 0.0, "paid_confirmed": 0.0})
        d["paid_marked"] += float(marked * ratio)
        d["paid_confirmed"] += float(confirmed * ratio)
    return result
