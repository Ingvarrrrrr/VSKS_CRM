"""Закупки по ЧАСТИ объединённой плановой позиции (владелец, 12.10.2026, план
merged-item-parts.md) — для GET /feo-categories/plan-positions: у каждого
элемента FeoPlannedItem.parts нужны «его» закупки (номер, статус, сумма,
оплачено), чтобы окно выбора импорта факта и «План закупок» показывали
позицию раскрытой на части с привязанными закупками, а не только общий
список закупок позиции целиком.

Группировка ТА ЖЕ (PLANNED_STATUSES, не остановлена), что и
feo_plan_fact.planned_item_consumption.linked_purchases — просто по другому
измерению (feo_plan_part_key вместо суммы по всей позиции); второй движок
расхода плана здесь не заводится (ПРАВИЛО №6) — эта функция ничего не вычитает
из остатка, только отображение «что уже закуплено по этой части».
"""
from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem


async def planned_item_part_purchases(
    db: AsyncSession, item_ids: list[int], exclude_purchase_id: int | None = None,
) -> dict[int, dict[str, list[dict]]]:
    """{feo_planned_item_id: {part_key: [{id, registry_number, status,
    status_label, amount, paid}]}} — только строки с заполненным
    feo_plan_part_key (часть не выбрана → закупка не попадает ни в одну
    часть, видна только в общем списке позиции, как и раньше)."""
    result: dict[int, dict[str, list[dict]]] = {iid: {} for iid in item_ids}
    if not item_ids:
        return result

    from app.routers.purchase_budget import PLANNED_STATUSES  # local: avoid router import cycle
    from app.routers.purchase_export import _STATUS_LABELS as _PURCHASE_STATUS_LABELS

    q = (
        select(
            PurchaseItem.feo_planned_item_id,
            PurchaseItem.feo_plan_part_key,
            PurchaseItem.purchase_id,
            Purchase.registry_number,
            Purchase.status,
            func.coalesce(func.sum(PurchaseItem.total_price), 0).label("amount"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
        .where(PurchaseItem.feo_plan_part_key.isnot(None))
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(Purchase.stopped_at.is_(None))
    )
    if exclude_purchase_id is not None:
        q = q.where(PurchaseItem.purchase_id != exclude_purchase_id)
    q = q.group_by(
        PurchaseItem.feo_planned_item_id, PurchaseItem.feo_plan_part_key,
        PurchaseItem.purchase_id, Purchase.registry_number, Purchase.status,
    )
    for r in (await db.execute(q)).all():
        by_part = result.setdefault(r.feo_planned_item_id, {})
        by_part.setdefault(r.feo_plan_part_key, []).append({
            "id": r.purchase_id,
            "registry_number": r.registry_number,
            "status": r.status,
            "status_label": _PURCHASE_STATUS_LABELS.get(r.status, r.status),
            "amount": float(r.amount),
        })

    # Оплата — Σ Payment по закупкам, попавшим хоть в одну часть (та же логика
    # «оплачено по закупке», что и на карточке закупки; второй расчёт оплаты
    # по позиции не заводим — тут только пометка «есть оплата», а не разнесение
    # суммы оплаты по частям, которая GALA вообще не ведёт построчно).
    purchase_ids = {
        p["id"]
        for parts in result.values()
        for lst in parts.values()
        for p in lst
    }
    if purchase_ids:
        from app.models.payment import Payment
        paid_q = (
            select(Payment.purchase_id, func.coalesce(func.sum(Payment.amount), 0))
            .where(Payment.purchase_id.in_(purchase_ids))
            .group_by(Payment.purchase_id)
        )
        paid_by_purchase = {pid: float(amt) for pid, amt in (await db.execute(paid_q)).all()}
        for parts in result.values():
            for lst in parts.values():
                for p in lst:
                    p["paid"] = paid_by_purchase.get(p["id"], 0.0)

    return result
