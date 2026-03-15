from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.contractor import Contractor
from app.models.user import User
from app.auth.jwt import get_current_user, get_org_filter
from typing import Optional

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _get_period_dates(period: str, ref_date: date):
    """Calculate start and end dates for a period."""
    if period == "week":
        start = ref_date - timedelta(days=ref_date.weekday())  # Monday
        end = start + timedelta(days=6)
    elif period == "month":
        start = ref_date.replace(day=1)
        # Last day of month
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
    elif period == "year":
        start = ref_date.replace(month=1, day=1)
        end = ref_date.replace(month=12, day=31)
    else:
        start = ref_date - timedelta(days=7)
        end = ref_date
    return start, end


def _apply_org_filter(q, user: User):
    org_ids = get_org_filter(user)
    if org_ids is not None:
        q = q.where(Purchase.subsidy_id.in_(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        ))
    return q


def _purchase_to_dict(p, contractors: dict, subsidies: dict, users: dict):
    return {
        "id": p.id,
        "subject": p.subject or p.item_name or "",
        "status": p.status,
        "purchase_number": p.purchase_number,
        "registry_number": p.registry_number,
        "planned_total_price": float(p.planned_total_price or 0),
        "contract_price": float(p.contract_price or 0),
        "payment_amount": float(p.payment_amount or 0),
        "execution_term": str(p.execution_term) if p.execution_term else None,
        "delivery_date": str(p.delivery_date) if p.delivery_date else None,
        "contractor_name": contractors.get(p.contractor_id, ""),
        "subsidy_name": subsidies.get(p.subsidy_id, ""),
        "assigned_user_name": users.get(p.assigned_user_id, ""),
        "task_comment": p.task_comment,
    }


@router.get("/summary")
async def report_summary(
    period: str = Query("week", regex="^(week|month|year)$"),
    ref_date: Optional[str] = Query(None),
    subsidy_id: Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = date.fromisoformat(ref_date) if ref_date else date.today()
    start, end = _get_period_dates(period, today)

    # Load lookup tables
    contractors_r = await db.execute(select(Contractor.id, Contractor.name))
    contractors = {r.id: r.name for r in contractors_r}
    subsidies_r = await db.execute(select(Subsidy.id, Subsidy.name))
    subsidies = {r.id: r.name for r in subsidies_r}
    users_r = await db.execute(select(User.id, User.full_name, User.username, User.department))
    users = {r.id: r.full_name or r.username for r in users_r}

    # Department filter: find user IDs belonging to the department
    dept_user_ids = None
    if department:
        dept_user_ids = {r.id for r in users_r if r.department and r.department.lower() == department.lower()}

    def _extra_filters(q):
        """Apply subsidy_id and department filters."""
        if subsidy_id is not None:
            q = q.where(Purchase.subsidy_id == subsidy_id)
        if dept_user_ids is not None:
            q = q.where(Purchase.assigned_user_id.in_(dept_user_ids))
        return q

    # Active purchases (in_progress, contracted)
    active_q = _extra_filters(_apply_org_filter(
        select(Purchase).where(Purchase.status.in_(["in_progress", "contracted"])),
        current_user
    ))
    active_result = await db.execute(active_q)
    active = [_purchase_to_dict(p, contractors, subsidies, users) for p in active_result.scalars().all()]

    # Completed in period (status=paid, payment_date in range)
    completed_q = _extra_filters(_apply_org_filter(
        select(Purchase)
        .where(Purchase.status == "paid")
        .where(Purchase.payment_doc_date.between(start, end)),
        current_user
    ))
    completed_result = await db.execute(completed_q)
    completed = [_purchase_to_dict(p, contractors, subsidies, users) for p in completed_result.scalars().all()]

    # Planned (status=planned or confirmed, created/updated in period — use id proxy)
    planned_q = _extra_filters(_apply_org_filter(
        select(Purchase)
        .where(Purchase.status.in_(["planned", "confirmed"])),
        current_user
    ))
    planned_result = await db.execute(planned_q)
    planned = [_purchase_to_dict(p, contractors, subsidies, users) for p in planned_result.scalars().all()]

    # Upcoming deadlines (execution_term in next period)
    next_start, next_end = _get_period_dates(period, end + timedelta(days=1))
    upcoming_q = _extra_filters(_apply_org_filter(
        select(Purchase)
        .where(Purchase.execution_term.between(next_start, next_end))
        .where(Purchase.status.notin_(["paid", "delivered"])),
        current_user
    ))
    upcoming_result = await db.execute(upcoming_q)
    upcoming = [_purchase_to_dict(p, contractors, subsidies, users) for p in upcoming_result.scalars().all()]

    # Overdue
    overdue_q = _extra_filters(_apply_org_filter(
        select(Purchase)
        .where(Purchase.execution_term < today)
        .where(Purchase.status.notin_(["paid", "delivered"])),
        current_user
    ))
    overdue_result = await db.execute(overdue_q)
    overdue = [_purchase_to_dict(p, contractors, subsidies, users) for p in overdue_result.scalars().all()]

    # Totals
    totals = {
        "planned_count": len(planned),
        "planned_sum": sum(p["planned_total_price"] for p in planned),
        "active_count": len(active),
        "active_sum": sum(p["contract_price"] or p["planned_total_price"] for p in active),
        "completed_count": len(completed),
        "completed_sum": sum(p["payment_amount"] for p in completed),
        "upcoming_count": len(upcoming),
        "overdue_count": len(overdue),
    }

    return {
        "period": period,
        "start_date": str(start),
        "end_date": str(end),
        "planned": planned,
        "active": active,
        "completed": completed,
        "upcoming": upcoming,
        "overdue": overdue,
        "totals": totals,
    }
