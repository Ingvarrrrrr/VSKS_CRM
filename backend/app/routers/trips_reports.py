"""
Trips — статистика журнала ПЛ и авто-заполнение остатка топлива.

Сосед app/routers/trips.py (Правило №5, резка монолита, сессия 2026-09-08).
ПЕРЕНЕСЕНО без изменений. Тот же префикс /api/trips.

ВАЖНО: регистрируется в app/routes.py ДО app.routers.trips (ядро) — иначе
Starlette матчит literal "stats"/"last-fuel" на catch-all GET /{trip_id} ядра,
и FastAPI падает 422 при попытке привести их к int (см. комментарии на местах
исходных эндпоинтов до резки).

Endpoints:
  GET /api/trips/stats       — total/active/on_review/closed/overdue counts
  GET /api/trips/last-fuel   — последний остаток топлива для авто-заполнения
                                fuel_remaining_start формы нового ПЛ (Phase 30.2)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_tab
from app.models.user import User
from app.models.trip import Trip

router = APIRouter(prefix="/api/trips", tags=["vehicles"])


# ─────────────────────── GET /api/trips/stats ───────────────────────────────
# NOTE: Must be declared BEFORE /{trip_id} to avoid FastAPI matching "stats" as int

@router.get("/stats")
async def waybill_stats(
    period: str = Query("month", description="day|week|month|year|all"),
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """KPI для журнала путевых листов: total, active, on_review, closed, overdue counts."""
    from datetime import date, timedelta
    from sqlalchemy import func as sql_func, case

    today = date.today()
    if period == "day":
        date_from = today
    elif period == "week":
        date_from = today - timedelta(days=7)
    elif period == "month":
        date_from = today.replace(day=1)
    elif period == "year":
        date_from = today.replace(month=1, day=1)
    else:
        date_from = None

    q = select(
        sql_func.count(Trip.id).label("total_count"),
        sql_func.count(
            case((Trip.status.in_(["tech_inspect", "med_inspect", "in_progress"]), Trip.id))
        ).label("active_count"),
        sql_func.count(
            case((Trip.status == "on_review", Trip.id))
        ).label("on_review_count"),
        sql_func.count(
            case((Trip.status == "closed", Trip.id))
        ).label("closed_count"),
        sql_func.count(
            case((Trip.status == "overdue", Trip.id))
        ).label("overdue_count"),
    ).select_from(Trip)

    if date_from is not None:
        q = q.where(Trip.date >= date_from)

    result = await db.execute(q)
    row = result.one()
    return {
        "period": period,
        "total_count": row.total_count,
        "active_count": row.active_count,
        "on_review_count": row.on_review_count,
        "closed_count": row.closed_count,
        "overdue_count": row.overdue_count,
    }


# ─────────────────────── GET /api/trips/last-fuel ───────────────────────────
# Phase 30.2: must be declared BEFORE /{trip_id} to avoid matching "last-fuel" as int

@router.get("/last-fuel")
async def last_fuel_for_vehicle(
    vehicle_id: int = Query(..., description="ID ТС"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_tab("vehicles")),
):
    """Phase 30.2: последний остаток топлива при заезде для этой машины
    (для авто-заполнения fuel_remaining_start формы нового ПЛ)."""
    res = await db.execute(
        select(Trip.fuel_remaining_finish, Trip.date, Trip.number)
        .where(
            Trip.vehicle_id == vehicle_id,
            Trip.fuel_remaining_finish.isnot(None),
            Trip.status.in_(["closed", "on_review"]),
        )
        .order_by(Trip.date.desc())
        .limit(1)
    )
    row = res.first()
    if not row:
        return {"fuel_remaining_l": None, "from_waybill_number": None, "from_date": None}
    return {
        "fuel_remaining_l": float(row[0]) if row[0] is not None else None,
        "from_waybill_number": row[2],
        "from_date": row[1].isoformat() if row[1] else None,
    }
