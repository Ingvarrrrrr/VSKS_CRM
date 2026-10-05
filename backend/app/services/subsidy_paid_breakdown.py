"""subsidy_paid_breakdown.py — «Оплачено» карточки субсидии (/dashboard/charts
subsidy_stats), ДВЕ величины словами владельца (05.10.2026): «по отметке
сотрудников» и «подтверждено выпиской», каждая с разбивкой товары/услуги.

ПРАВИЛО №6 — не вторая формула «оплаты»: источник значений ровно тот же, что
уже утверждён и покрыт тестом для дерева ФЭО
(app/services/feo_plan_payments.py::paid_consumption_by_category, см. его
докстринг и tests/test_paid_confirmed_vs_declared_tree.py) —
Purchase.payment_amount_declared (ручная отметка, НЕ подтверждена выпиской) и
Purchase.payment_amount (подтверждено выпиской, Payment.confirmed_by_statement=
True) — обе колонки пишет app.services.purchase_payments::
recompute_purchase_payments, эта функция только агрегирует их на уровень
субсидии и делит по типу (товар/услуга).

Отличие от dashboard_type_split.py::"paid"-этапа (widget.paid): тот считает
ТОЛЬКО закупки со status='paid' (жёсткий статус, выставляется подтверждением
согласующего) — другая величина, карточка её не теряет (остаётся total_paid/
widget.paid как есть). Здесь — ЛЮБАЯ закупка в PLANNED_STATUSES с отметкой или
подтверждением платежа, независимо от итогового статуса (ровно то же
множество строк, что видит дерево ФЭО).

Область агрегации (scope) — ТА ЖЕ, что у остальных статусных сумм карточки:
Purchase.stopped_at IS NULL + aggregate_scope_expr() (не задваивает рамочные
головы с реальными детьми, см. app/services/purchase_amounts.py).

Точность разбивки товары/услуги (правка 05.10.2026, ревью владельца —
«Заказано/Поставлено уже 0,00, переиспользуй тот же механизм»): raw-доли по
purchase_type_shares() копятся НЕРАСКРУГЛЁННЫМИ Decimal по ВСЕМ закупкам
субсидии, округление до копейки — РОВНО ОДИН РАЗ в конце, через
app.services.dashboard_type_split.reconcile_split(raw, target) — ТУ ЖЕ
функцию, которой уже пользуются «Заказано»/«Поставлено»/контракты (Правило
№6 — вторая функция округления долей здесь не заводится). Сумма
goods+services+unspecified конструктивно равна declared/confirmed субсидии
ровно, без дробных копеек.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.dashboard_type_split import reconcile_split
from app.services.item_type_split import TypeShares, purchase_type_shares
from app.services.purchase_amounts import aggregate_scope_expr
from sqlalchemy import or_ as sqlor

PLANNED_STATUSES: set = {"plan_schedule", "work_in_progress", "contracted", "ordered", "delivered", "paid"}


def _zero3() -> List[Decimal]:
    return [Decimal(0), Decimal(0), Decimal(0)]


async def paid_breakdown_by_subsidy(db: AsyncSession, subsidy_ids: List[int]) -> Dict[int, dict]:
    """{subsidy_id: {declared, confirmed, declared_by_kind, confirmed_by_kind}}

    declared — Σ «оплачено по отметке сотрудников» (payment_amount_declared +
    payment_amount, та же сумма, что paid_marked в дереве ФЭО — отметка
    включает И неподтверждённое, И уже подтверждённое, подтверждение не
    «отменяет» то, что человек когда-то отметил).
    confirmed — Σ «подтверждено выпиской» (payment_amount, ТОЛЬКО
    confirmed_by_statement=True)."""
    result: Dict[int, dict] = {}
    if not subsidy_ids:
        return result

    stmt = (
        select(
            Purchase.id.label("purchase_id"),
            Purchase.subsidy_id,
            Purchase.payment_amount,
            Purchase.payment_amount_declared,
        )
        .where(Purchase.subsidy_id.in_(subsidy_ids))
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(Purchase.stopped_at.is_(None))
        .where(aggregate_scope_expr())
        .where(sqlor(Purchase.payment_amount.isnot(None), Purchase.payment_amount_declared.isnot(None)))
    )
    purchases = (await db.execute(stmt)).all()
    if not purchases:
        return result

    purchase_ids = [r.purchase_id for r in purchases]
    items_q = (
        select(PurchaseItem.purchase_id, PurchaseItem.item_type, PurchaseItem.total_price)
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
    )
    items_by_purchase: Dict[int, list] = {}
    for row in (await db.execute(items_q)).all():
        items_by_purchase.setdefault(row.purchase_id, []).append(row)

    # totals[subsidy_id] = (declared_total, confirmed_total, raw_declared[3], raw_confirmed[3])
    totals: Dict[int, dict] = {}
    for r in purchases:
        declared = Decimal(str(r.payment_amount or 0)) + Decimal(str(r.payment_amount_declared or 0))
        confirmed = Decimal(str(r.payment_amount or 0))
        if declared == 0 and confirmed == 0:
            continue

        t = totals.setdefault(r.subsidy_id, {
            "declared": Decimal(0), "confirmed": Decimal(0),
            "raw_declared": _zero3(), "raw_confirmed": _zero3(),
        })
        t["declared"] += declared
        t["confirmed"] += confirmed

        items = items_by_purchase.get(r.purchase_id, [])
        shares: TypeShares = purchase_type_shares(items)
        for acc, amt in ((t["raw_declared"], declared), (t["raw_confirmed"], confirmed)):
            acc[0] += amt * shares.goods
            acc[1] += amt * shares.services
            acc[2] += amt * shares.unspecified

    for sid, t in totals.items():
        result[sid] = {
            "declared": float(t["declared"]),
            "confirmed": float(t["confirmed"]),
            "declared_by_kind": reconcile_split(t["raw_declared"], t["declared"]),
            "confirmed_by_kind": reconcile_split(t["raw_confirmed"], t["confirmed"]),
        }
    return result
