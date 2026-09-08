"""GET /api/dashboard/analytics — сосед dashboard.py (Правило №5, резка 1641→core, 2026-09-08).

Воронка закупок, помесячные оплаты, топ-контрагенты, план/факт по субсидиям
и производные метрики для дашборда.
"""
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case, extract
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.contractor import Contractor
from app.models.user import User
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import get_visible_subsidy_ids
from app.routers.dashboard import _UNSET

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/analytics")
async def analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    subsidy_ids: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
):
    today = date.today()
    org_ids = get_org_filter(current_user)
    dash_sids = _UNSET
    if scope == "dashboard":
        dash_sids = await get_visible_subsidy_ids(current_user, db, "dashboard")
    sid_filter = [int(x) for x in subsidy_ids.split(",") if x.strip()] if subsidy_ids else None

    def _pf(q):
        """Apply purchase org/dashboard + subsidy filter inline."""
        if dash_sids is not _UNSET:
            if dash_sids is not None:
                q = q.where(Purchase.subsidy_id.in_(dash_sids))
        elif org_ids is not None:
            q = q.where(Purchase.subsidy_id.in_(
                select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
            ))
        if sid_filter:
            q = q.where(Purchase.subsidy_id.in_(sid_filter))
        return q

    # 1. Purchase funnel
    STATUS_ORDER = ["wishes", "plan_schedule", "work_in_progress", "contracted", "delivered", "paid"]
    funnel_result = await db.execute(_pf(
        select(Purchase.status, func.count(Purchase.id).label("cnt"),
               func.coalesce(func.sum(Purchase.planned_total_price), 0).label("total"))
        .group_by(Purchase.status)
    ))
    funnel_raw = {r.status: {"count": r.cnt, "total": float(r.total)} for r in funnel_result}
    funnel = [{"status": s, "count": funnel_raw.get(s, {}).get("count", 0),
               "total": funnel_raw.get(s, {}).get("total", 0.0)} for s in STATUS_ORDER]

    # 2. Monthly paid amounts (last 12 months)
    monthly_result = await db.execute(_pf(
        select(
            extract("year", Purchase.payment_doc_date).label("y"),
            extract("month", Purchase.payment_doc_date).label("m"),
            func.coalesce(func.sum(Purchase.payment_amount), 0).label("total"),
        )
        .where(Purchase.payment_doc_date != None)
        .group_by("y", "m")
        .order_by("y", "m")
    ))
    monthly = [{"year": int(r.y), "month": int(r.m), "total": float(r.total)} for r in monthly_result]

    # 3. Top 10 contractors by total purchase value
    # ORDER BY must sort on the SAME coalesced expression as the selected "total" —
    # sorting on the raw (non-coalesced) SUM sent contractors whose sole purchase has
    # planned_total_price=NULL to the TOP of a DESC order (Postgres default: NULLS
    # FIRST for DESC), even though they display as "0" — found live (2026-09-04) via
    # /api/dashboard/analytics: top_contractors[0].total was 0 while real top spenders
    # (13.9M+) were pushed down. Frontend uses top_contractors[0] as the 100%-bar
    # reference (analyticsMaxContractor/maxContractor) — a 0 there divided every other
    # contractor's bar by zero (now also hardened with safeDiv, but the ranking itself
    # was simply wrong).
    top_contractors_total = func.coalesce(func.sum(Purchase.planned_total_price), 0)
    top_result = await db.execute(_pf(
        select(
            Contractor.name,
            func.count(Purchase.id).label("cnt"),
            top_contractors_total.label("total"),
        )
        .join(Contractor, Purchase.contractor_id == Contractor.id)
        .group_by(Contractor.name)
        .order_by(top_contractors_total.desc())
        .limit(10)
    ))
    top_contractors = [{"name": r.name, "count": r.cnt, "total": float(r.total)} for r in top_result]

    # 4. Upcoming deliveries (next 30 days)
    upcoming_result = await db.execute(_pf(
        select(func.count(Purchase.id).label("cnt"),
               func.coalesce(func.sum(Purchase.planned_total_price), 0).label("total"))
        .where(Purchase.delivery_date.between(today, today + timedelta(days=30)))
    ))
    upcoming = upcoming_result.one()

    # 5. Plan vs contract delta — Σ(план − договор) aggregate for the dashboard.
    # NOT the same metric as the manual per-purchase Purchase.economy field
    # ("Экономия"): this is a computed sum across purchases, that one is a
    # user-entered value. Keeping distinct names (plan_contract_delta vs
    # economy) per ПРАВИЛО №6 — one indicator, one name, one source.
    plan_contract_delta_result = await db.execute(_pf(
        select(func.coalesce(func.sum(Purchase.planned_total_price - Purchase.contract_price), 0))
        .where(Purchase.contract_price != None)
        .where(Purchase.contract_price > 0)
    ))
    plan_contract_delta = float(plan_contract_delta_result.scalar() or 0)

    # 6. Overdue purchases (execution_term past, not paid/delivered)
    overdue_result = await db.execute(_pf(
        select(func.count(Purchase.id))
        .where(Purchase.execution_term < today)
        .where(Purchase.status.notin_(["paid", "delivered"]))
    ))
    overdue_count = overdue_result.scalar() or 0

    # 7. Upcoming deadlines (next 30 days) — detailed list
    deadlines_result = await db.execute(_pf(
        select(Purchase.id, Purchase.subject, Purchase.item_name,
               Purchase.purchase_number, Purchase.execution_term, Purchase.status)
        .where(Purchase.execution_term.between(today, today + timedelta(days=30)))
        .where(Purchase.status.notin_(["paid", "delivered"]))
        .order_by(Purchase.execution_term)
        .limit(20)
    ))
    upcoming_deadlines = [
        {"id": r.id, "name": r.subject or r.item_name or f"Закупка #{r.purchase_number or r.id}",
         "purchase_number": r.purchase_number, "execution_term": str(r.execution_term), "status": r.status}
        for r in deadlines_result
    ]

    # 8. Purchase method distribution
    method_result = await db.execute(_pf(
        select(Purchase.purchase_method, func.count(Purchase.id).label("cnt"))
        .group_by(Purchase.purchase_method)
    ))
    method_distribution = {(r.purchase_method or "unknown"): r.cnt for r in method_result}

    # 9. Plan vs Fact per subsidy
    pf_q = (
        select(
            Subsidy.name,
            func.coalesce(func.sum(Purchase.planned_total_price), 0).label("plan"),
            func.coalesce(func.sum(
                case((Purchase.status.in_(["contracted", "delivered", "paid"]), Purchase.contract_price), else_=None)
            ), 0).label("contracted"),
            func.coalesce(func.sum(
                case((Purchase.status == "paid", Purchase.payment_amount), else_=None)
            ), 0).label("paid"),
        )
        .select_from(Subsidy)
        .outerjoin(Purchase, Purchase.subsidy_id == Subsidy.id)
        .group_by(Subsidy.id, Subsidy.name)
        .order_by(Subsidy.name)
    )
    if dash_sids is not _UNSET:
        if dash_sids is not None:
            pf_q = pf_q.where(Subsidy.id.in_(dash_sids))
    elif org_ids is not None:
        pf_q = pf_q.where(Subsidy.org_id.in_(org_ids))
    if sid_filter:
        pf_q = pf_q.where(Subsidy.id.in_(sid_filter))
    pf_result = await db.execute(pf_q)
    plan_fact = [
        {"subsidy": r.name, "plan": float(r.plan), "contracted": float(r.contracted), "paid": float(r.paid)}
        for r in pf_result
    ]

    return {
        "funnel": funnel,
        "monthly_payments": monthly,
        "top_contractors": top_contractors,
        "upcoming_deliveries": {"count": upcoming.cnt, "total": float(upcoming.total)},
        "plan_contract_delta": plan_contract_delta,
        "overdue_count": overdue_count,
        "upcoming_deadlines": upcoming_deadlines,
        "method_distribution": method_distribution,
        "plan_fact": plan_fact,
    }
