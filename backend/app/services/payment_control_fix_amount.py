"""«Исправить сумму закупки на сумму из выписки» — план
.planning/quick/2026-10-06-statement-control/PLAN.md, п.4.

Вызывается ТОЛЬКО из POST .../payment-control/bank-payments/{bp_id}/attach
(fix_amount=true) — владелец: предлагать правку суммы ТОЛЬКО когда она
безопасна (закупка с одной позицией, или расхождение в пределах рубля —
правится последняя позиция). ПРАВИЛО №6: пересчёт денежных колонок делает
ЕДИНСТВЕННЫЙ писатель app/services/purchase_money_writer.py::
recalc_purchase_money — здесь только правится позиция (ContractItem, если
есть, иначе PurchaseItem) и зовётся он же, второго пересчёта не заводится.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_item import ContractItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.purchase_money_writer import recalc_purchase_money

AMOUNT_TOL = Decimal("0.02")
FIX_DELTA_LIMIT = Decimal("1.00")


class AmountFixNotAllowed(Exception):
    """Закупку нельзя поправить автоматически — несколько позиций и
    расхождение больше рубля. Router превращает в HTTP 422."""


async def fix_purchase_amount(db: AsyncSession, purchase: Purchase, new_total: Decimal) -> dict:
    """Правит сумму договора закупки на new_total (сумма строки выписки).
    Возвращает {"from": ..., "to": ...} (float). Бросает AmountFixNotAllowed,
    если условие безопасности (1 позиция ИЛИ |Δ| ≤ 1 ₽) не выполнено."""
    contract_items = (await db.execute(
        select(ContractItem).where(ContractItem.purchase_id == purchase.id)
    )).scalars().all()
    purchase_items = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id)
    )).scalars().all()

    items = contract_items or purchase_items
    current_total = (
        sum((Decimal(str(i.total if contract_items else i.total_price)) for i in items), Decimal(0))
        if items
        else Decimal(str(purchase.contract_price or 0))
    )
    delta = new_total - current_total

    if abs(delta) <= AMOUNT_TOL:
        return {"from": float(current_total), "to": float(new_total)}

    if len(items) > 1 and abs(delta) > FIX_DELTA_LIMIT:
        raise AmountFixNotAllowed(
            f"У закупки {len(items)} позиции(й), расхождение {delta:.2f} ₽ "
            "больше рубля — автоматическая правка суммы невозможна, уточните позиции вручную"
        )

    if contract_items:
        last = contract_items[-1]
        last.total = Decimal(str(last.total or 0)) + delta
        await db.flush()
        # Пересчёт перезагрузит Σ ContractItem сам (не передаём явно) —
        # recalc_purchase_money пишет её в contract_price, см. докстринг модуля.
        await recalc_purchase_money(db, purchase)
    elif purchase_items:
        last = purchase_items[-1]
        last.total_price = Decimal(str(last.total_price or 0)) + delta
        await db.flush()
        # Нет ContractItem — цена договора правится не формулой recalc (та не
        # трогает contract_price, если он уже заполнен), а прямо: именно это
        # число и есть «сумма из выписки», которую согласился принять владелец.
        purchase.contract_price = new_total
        await recalc_purchase_money(db, purchase)
    else:
        purchase.contract_price = new_total

    return {"from": float(current_total), "to": float(new_total)}
