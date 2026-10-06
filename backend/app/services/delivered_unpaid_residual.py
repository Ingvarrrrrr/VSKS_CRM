"""delivered_unpaid_residual.py — «непогашенный остаток поставленного» по
закупке, единственный источник карточки «Поставлено, не оплачено»
(dashboard_charts.py) и её drill/Excel-расшифровки (dashboard_type_drill.py).

Повод (владелец, 06.10.2026, ФАДМ 2026_2, прод id=89): карточка показывала
2 271 211,09 (товары 130 821,29 / услуги 2 140 389,80) — ОДНО вычитание на
уровне субсидии (Σ«Поставлено» − Σ«Оплачено по отметке»), а клик по строке
«товары» открывал СТАРЫЙ drill (dashboard_type_split.py::compute_type_split_detail,
stage="delivered_unpaid") — тот берёт ВСЕ закупки status='delivered' целиком, не
глядя на оплату вообще (35 строк, Σ 2 599 247 — полный «Поставлено», а не
остаток). Прод-факт (SELECT, 06.10.2026): у subsidy_id=89 подавляющее
большинство закупок delivered УЖЕ имеют payment_amount == сумме закупки (платёж
отмечен, статус просто не переведён в 'paid') — непогашены лишь немногие (id
3023/3024/3063-3065/3114-3116/3121/3139/3141/3157/3161-3162/3175/3179-3182/
3191-3195/3197 и т.п.), поэтому «остаток» на порядок меньше «Поставлено
целиком» — драматическое расхождение объясняется именно этим, а не ошибкой
долей по типу.

ПРАВИЛО №6 — не вторая формула «Поставлено» и не вторая формула «Оплачено»:
- «поставлено по закупке» — effective_amount_expr() (app.services.purchase_amounts,
  тот же, что _stage_contributions в dashboard_type_split.py считает как вклад
  статусов delivered/paid в этап "delivered"), ограничено aggregate_scope_expr()
  (не задваивает рамочные головы с реальными детьми).
- «оплачено по закупке» — Purchase.payment_amount + Purchase.payment_amount_declared
  (РОВНО то же, что subsidy_paid_breakdown.py называет «declared» — «по отметке
  сотрудников», источник purchase_payments.py::recompute_purchase_payments).
- остаток = max(0, поставлено − оплачено) НА УРОВНЕ ОДНОЙ ЗАКУПКИ (не на
  уровне субсидии!) — переплата по одной закупке НЕ уменьшает долг другой
  (ровно жалоба владельца: прежняя формула вычитала Σ оплачено из Σ поставлено
  субсидии целиком, так что закупка с предоплатой «гасила» долг за другую,
  ещё не оплаченную).
- разбивка по типу — purchase_type_shares()/reconcile_split() (item_type_split.py/
  dashboard_type_split.py, тот же механизм, что все остальные показатели
  карточки), применённые к ОСТАТКУ закупки (не к полной сумме «Поставлено»).

Только status IN ('delivered','paid') — ровно те статусы, что _stage_contributions
засчитывает в накопительный этап "delivered" (владелец, docstring dashboard_
type_split.py); 'paid'-закупки обычно полностью оплачены (остаток 0 по
построению), но не исключаются явно — на случай частичной оплаты даже в этом
статусе (нет второго if, формула одна для обеих).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.dashboard_type_split import reconcile_split
from app.services.item_type_split import TypeShares, purchase_type_shares
from app.services.purchase_amounts import aggregate_scope_expr, effective_amount_expr

DELIVERED_UNPAID_STATUSES: tuple = ("delivered", "paid")


def _zero3() -> List[Decimal]:
    return [Decimal(0), Decimal(0), Decimal(0)]


async def _residual_rows(
    db: AsyncSession, *, subsidy_ids: Optional[List[int]] = None, purchase_ids: Optional[List[int]] = None,
):
    """Строки (purchase_id, subsidy_id, delivered_amt, paid_amt) в скоупе
    DELIVERED_UNPAID_STATUSES — общий загрузчик для per-subsidy агрегата и для
    построчного drill (не два разных запроса с риском разъехаться)."""
    stmt = (
        select(
            Purchase.id.label("purchase_id"),
            Purchase.subsidy_id,
            effective_amount_expr().label("delivered_amt"),
            Purchase.payment_amount,
            Purchase.payment_amount_declared,
        )
        .where(Purchase.status.in_(DELIVERED_UNPAID_STATUSES))
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
    return (await db.execute(stmt)).all()


async def delivered_unpaid_residual_by_subsidy(db: AsyncSession, subsidy_ids: List[int]) -> Dict[int, dict]:
    """{subsidy_id: {"total": float, "by_kind": {"goods","services","unspecified"}}}

    total — Σ остатков закупок субсидии (каждый остаток уже не отрицателен —
    переплата по одной закупке не переносится на другую, см. докстринг модуля).
    by_kind — та же раскладка по типу позиций, что и у остальных карточек
    (reconcile_split против уже посчитанного total, Правило №6 — округление до
    копейки ровно один раз)."""
    result: Dict[int, dict] = {}
    if not subsidy_ids:
        return result

    rows = await _residual_rows(db, subsidy_ids=subsidy_ids)
    if not rows:
        return result

    purchase_ids = [r.purchase_id for r in rows]
    items_q = (
        select(PurchaseItem.purchase_id, PurchaseItem.item_type, PurchaseItem.total_price)
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
    )
    items_by_purchase: Dict[int, list] = {}
    for row in (await db.execute(items_q)).all():
        items_by_purchase.setdefault(row.purchase_id, []).append(row)

    totals: Dict[int, dict] = {}
    for r in rows:
        delivered_amt = Decimal(str(r.delivered_amt)) if r.delivered_amt is not None else Decimal(0)
        paid_amt = Decimal(str(r.payment_amount or 0)) + Decimal(str(r.payment_amount_declared or 0))
        residual = delivered_amt - paid_amt
        if residual <= 0:
            continue

        t = totals.setdefault(r.subsidy_id, {"total": Decimal(0), "raw": _zero3()})
        t["total"] += residual

        shares: TypeShares = purchase_type_shares(items_by_purchase.get(r.purchase_id, []))
        t["raw"][0] += residual * shares.goods
        t["raw"][1] += residual * shares.services
        t["raw"][2] += residual * shares.unspecified

    for sid, t in totals.items():
        result[sid] = {
            "total": float(t["total"]),
            "by_kind": reconcile_split(t["raw"], t["total"]),
        }
    return result


async def delivered_unpaid_residual_detail(
    db: AsyncSession, *, apply_filter, visible_subsidy_ids: Optional[set],
) -> dict:
    """Построчная (по позициям закупки) раскладка остатка — для
    dashboard_type_drill.py (stage="delivered_unpaid") и Excel-выгрузки того же
    списка. Только закупки с residual > 0 (полностью оплаченные не попадают —
    требование владельца); сумма строки = доля ОСТАТКА, не полной суммы
    закупки (см. докстринг модуля — ПРАВИЛО №6 не плодит вторую формулу суммы
    закупки, только делит уже посчитанный residual между позициями тем же
    приёмом округления, что dashboard_type_split._split_amount_across_items).

    apply_filter — тот же колбэк видимости, что dashboard_type_drill.py уже
    применяет к base_q для остальных этапов (_apply_purchase_org_filter)."""
    from app.services.dashboard_type_split import _emit_item_rows  # местный импорт — тот же приём округления, не вторая копия

    base_q = (
        select(
            Purchase.id, Purchase.subsidy_id,
            effective_amount_expr().label("delivered_amt"),
            Purchase.payment_amount, Purchase.payment_amount_declared,
        )
        .where(Purchase.status.in_(DELIVERED_UNPAID_STATUSES))
        .where(Purchase.stopped_at.is_(None))
        .where(aggregate_scope_expr())
    )
    base_q = apply_filter(base_q)
    rows = (await db.execute(base_q)).all()

    purchase_ids = [r.id for r in rows]
    items_by_purchase: Dict[int, list] = {}
    if purchase_ids:
        items_q = (
            select(
                PurchaseItem.id, PurchaseItem.purchase_id, PurchaseItem.item_name,
                PurchaseItem.item_type, PurchaseItem.total_price,
            ).where(PurchaseItem.purchase_id.in_(purchase_ids))
        )
        for row in (await db.execute(items_q)).all():
            items_by_purchase.setdefault(row.purchase_id, []).append(row)

    out_rows: List[dict] = []
    raw = _zero3()
    for r in rows:
        delivered_amt = Decimal(str(r.delivered_amt)) if r.delivered_amt is not None else Decimal(0)
        paid_amt = Decimal(str(r.payment_amount or 0)) + Decimal(str(r.payment_amount_declared or 0))
        residual = delivered_amt - paid_amt
        if residual <= 0:
            continue
        _emit_item_rows(out_rows, raw, purchase_id=r.id, amt=residual, items=items_by_purchase.get(r.id, ()))

    return {"raw": raw, "rows": out_rows}
