"""paid_over_delivered.py — «оплачено сверх поставленного» по закупке,
единственный источник плашки дашборда «оплачено больше, чем поставлено»
(owner, 07.10.2026, прод id=74 «ЛНР»: карточки «Поставлено» 3 381 872,26 /
«Поставлено, не оплачено» 0,00 / «Оплачено» 3 385 009,26 — оплачено на 3 137
больше поставленного; причина — РЕЕ-2026-03421, status work_in_progress,
оплата по отметке (payment_amount_declared) 3 137, договора нет, т.е. «поставлено»
по этой закупке равно 0).

ПРАВИЛО №6 — зеркало delivered_unpaid_residual.py (прочитан целиком перед этим
модулем), ОДНА формула «поставлено»/«оплачено» на обе стороны одного и того же
сравнения, не вторая копия:
  - «поставлено по закупке» — effective_amount_expr() (app.services.
    purchase_amounts), НО ТОЛЬКО для status IN ('delivered','paid') — для
    любого статуса НИЖЕ (wishes/plan_schedule/contracted/ordered/
    work_in_progress/…) «поставлено» = 0 (поставки как факта ещё нет, чем бы
    ни был заполнен contract_price/planned_total_price — в отличие от
    delivered_unpaid_residual.py, этому модулю НЕЛЬЗЯ использовать
    effective_amount_expr() для статусов до delivered, та цепочка на этих
    статусах возвращает contract_price/planned_total_price, а не 0, и
    превышение замаскируется).
  - «оплачено по закупке» — Purchase.payment_amount + Purchase.
    payment_amount_declared (РОВНО та же пара колонок, тот же смысл «по
    отметке сотрудников», что delivered_unpaid_residual.py и
    subsidy_paid_breakdown.py).
  - excess = max(0, оплачено − поставлено) НА УРОВНЕ ОДНОЙ ЗАКУПКИ (не на
    уровне субсидии — переплата одной закупки НЕ гасит недоплату другой,
    та же логика, что и у delivered_unpaid_residual.py, зеркально).
  - aggregate_scope_expr() — тот же фильтр рамочных голов с реальными
    детьми (не задваивать).
  - разбивка по типу — purchase_type_shares()/reconcile_split(), тот же
    механизм, применённый к excess закупки (не к полной сумме «Оплачено»).

Scope — ВСЕ статусы (не только DELIVERED_UNPAID_STATUSES, см. docstring выше):
закупка со статусом work_in_progress/contracted/ordered с оплатой по отметке
обязана попасть в этот список (поставлено=0 < оплачено), delivered_unpaid_
residual.py её не видит вовсе (там scope — только delivered/paid).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.dashboard_type_split import reconcile_split
from app.services.delivered_unpaid_residual import DELIVERED_UNPAID_STATUSES
from app.services.item_type_split import TypeShares, purchase_type_shares
from app.services.purchase_amounts import aggregate_scope_expr, effective_amount_expr


def _zero3() -> List[Decimal]:
    return [Decimal(0), Decimal(0), Decimal(0)]


def _delivered_amount_expr():
    """«Поставлено по закупке» для ЭТОГО показателя — effective_amount_expr()
    ТОЛЬКО на статусах delivered/paid, иначе 0 (см. docstring модуля — почему
    нельзя взять effective_amount_expr() целиком, как delivered_unpaid_
    residual.py делает: та цепочка на более ранних статусах фолбэчится на
    contract_price/planned_total_price, а здесь «поставлено» до факта поставки
    обязано быть нулём, не планом/договором)."""
    return case(
        (Purchase.status.in_(DELIVERED_UNPAID_STATUSES), effective_amount_expr()),
        else_=0,
    )


def _reason(*, is_prepayment: bool, status: str, status_label: str, excess: Decimal, delivered_amt: Decimal) -> str:
    if is_prepayment:
        return "аванс (оплата до поставки)"
    if delivered_amt <= 0:
        return f'оплачено, но не поставлено (статус «{status_label}»)'
    return "оплачено больше суммы поставки"


async def _excess_rows(
    db: AsyncSession, *, subsidy_ids: Optional[List[int]] = None, purchase_ids: Optional[List[int]] = None,
):
    """Строки (purchase_id, subsidy_id, status, is_prepayment, delivered_amt,
    paid_amt) со excess > 0 — общий загрузчик для per-subsidy агрегата и для
    построчного списка плашки (не два разных запроса с риском разъехаться)."""
    stmt = (
        select(
            Purchase.id.label("purchase_id"),
            Purchase.subsidy_id,
            Purchase.status,
            Purchase.is_prepayment,
            Purchase.registry_number,
            Purchase.purchase_number,
            Purchase.subject,
            _delivered_amount_expr().label("delivered_amt"),
            Purchase.payment_amount,
            Purchase.payment_amount_declared,
        )
        .where(Purchase.stopped_at.is_(None))
        .where(aggregate_scope_expr())
    )
    if subsidy_ids is not None:
        if not subsidy_ids:
            return []
        stmt = stmt.where(Purchase.subsidy_id.in_(subsidy_ids))
    if purchase_ids is not None:
        if not purchase_ids:
            return []
        stmt = stmt.where(Purchase.id.in_(purchase_ids))

    rows = (await db.execute(stmt)).all()
    out = []
    for r in rows:
        delivered_amt = Decimal(str(r.delivered_amt)) if r.delivered_amt is not None else Decimal(0)
        paid_amt = Decimal(str(r.payment_amount or 0)) + Decimal(str(r.payment_amount_declared or 0))
        excess = paid_amt - delivered_amt
        if excess <= 0:
            continue
        out.append((r, delivered_amt, paid_amt, excess))
    return out


async def paid_over_delivered_by_subsidy(db: AsyncSession, subsidy_ids: List[int]) -> Dict[int, dict]:
    """{subsidy_id: {"total": float, "prepayment_total": float, "by_kind": {...}}}

    total — Σ excess по закупкам субсидии (каждый excess уже не отрицателен —
    см. docstring модуля). prepayment_total — та же сумма, но только по
    закупкам is_prepayment=True (владелец: «аванс законен, но виден отдельно»).
    """
    result: Dict[int, dict] = {}
    if not subsidy_ids:
        return result

    rows = await _excess_rows(db, subsidy_ids=subsidy_ids)
    if not rows:
        return result

    purchase_ids = [r.purchase_id for r, _, _, _ in rows]
    items_q = (
        select(PurchaseItem.purchase_id, PurchaseItem.item_type, PurchaseItem.total_price)
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
    )
    items_by_purchase: Dict[int, list] = {}
    for row in (await db.execute(items_q)).all():
        items_by_purchase.setdefault(row.purchase_id, []).append(row)

    totals: Dict[int, dict] = {}
    for r, delivered_amt, paid_amt, excess in rows:
        t = totals.setdefault(r.subsidy_id, {"total": Decimal(0), "prepayment_total": Decimal(0), "raw": _zero3()})
        t["total"] += excess
        if r.is_prepayment:
            t["prepayment_total"] += excess

        shares: TypeShares = purchase_type_shares(items_by_purchase.get(r.purchase_id, []))
        t["raw"][0] += excess * shares.goods
        t["raw"][1] += excess * shares.services
        t["raw"][2] += excess * shares.unspecified

    for sid, t in totals.items():
        result[sid] = {
            "total": float(t["total"]),
            "prepayment_total": float(t["prepayment_total"]),
            "by_kind": reconcile_split(t["raw"], t["total"]),
        }
    return result


async def paid_over_delivered_rows(
    db: AsyncSession, *, apply_filter, status_labels: Dict[str, str],
) -> dict:
    """Построчный список закупок с excess > 0 — для плашки на дашборде и её
    drill-диалога (owner: «список закупок», не только сумма).

    apply_filter — тот же колбэк видимости, что dashboard_type_drill.py уже
    применяет к base_q для остальных этапов (_apply_purchase_org_filter).
    status_labels — STATUS_LABELS (app.routers.purchase_transitions), чтобы не
    импортировать роутер из сервисного модуля на верхнем уровне.
    """
    base_q = (
        select(
            Purchase.id, Purchase.subsidy_id, Purchase.status, Purchase.is_prepayment,
            Purchase.registry_number, Purchase.purchase_number, Purchase.subject,
            _delivered_amount_expr().label("delivered_amt"),
            Purchase.payment_amount, Purchase.payment_amount_declared,
        )
        .where(Purchase.stopped_at.is_(None))
        .where(aggregate_scope_expr())
    )
    base_q = apply_filter(base_q)
    rows = (await db.execute(base_q)).all()

    out_rows: List[dict] = []
    total = Decimal(0)
    prepayment_total = Decimal(0)
    for r in rows:
        delivered_amt = Decimal(str(r.delivered_amt)) if r.delivered_amt is not None else Decimal(0)
        paid_amt = Decimal(str(r.payment_amount or 0)) + Decimal(str(r.payment_amount_declared or 0))
        excess = paid_amt - delivered_amt
        if excess <= 0:
            continue
        total += excess
        if r.is_prepayment:
            prepayment_total += excess
        status_label = status_labels.get(r.status, r.status)
        out_rows.append({
            "purchase_id": r.id,
            "subsidy_id": r.subsidy_id,
            "registry_number": r.registry_number,
            "purchase_number": r.purchase_number if r.purchase_number is not None else r.id,
            "subject": r.subject or "",
            "status": r.status,
            "status_label": status_label,
            "is_prepayment": bool(r.is_prepayment),
            "delivered": float(delivered_amt),
            "paid": float(paid_amt),
            "excess": float(excess),
            "reason": _reason(
                is_prepayment=bool(r.is_prepayment), status=r.status, status_label=status_label,
                excess=excess, delivered_amt=delivered_amt,
            ),
        })

    out_rows.sort(key=lambda row: row["excess"], reverse=True)
    return {
        "total": float(total),
        "prepayment_total": float(prepayment_total),
        "purchases_count": len(out_rows),
        "rows": out_rows,
    }
