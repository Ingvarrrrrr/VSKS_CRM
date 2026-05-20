"""
Vehicles Dashboard aggregation router — Plan 29-10, Phase 29.

Decisions covered: D-16 (KPI cards), D-17 (maintenance warnings), D-18 (repair cost).

Endpoints (all GET, all require_tab('vehicles'), all apply visibility filter):
  /api/vehicles-dashboard/kpi                — 4 KPI cards
  /api/vehicles-dashboard/fuel-canister      — SVG canister widget
  /api/vehicles-dashboard/in-repair         — list of vehicles in active repair
  /api/vehicles-dashboard/maintenance-warning — warning list
  /api/vehicles-dashboard/by-org             — bar chart by org
  /api/vehicles-dashboard/fuel-by-period     — line chart (fuel over time)
  /api/vehicles-dashboard/state-donut        — donut chart by vehicle state
  /api/vehicles-dashboard/top-expenses       — TOP-10 vehicles by expenses

Multi-tenancy: all queries filtered via _visibility_clause (D-06).
Registration in __init__.py done in a separate commit after Wave 1 (per plan).
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.permissions import require_tab
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.vehicle_repair import VehicleRepair
from app.models.vehicle_attachment import VehicleAttachment
from app.models.fuel_log import FuelLog
from app.models.trip import Trip
from app.models.external_driver import ExternalDriver
from app.models.organization import Organization

router = APIRouter(prefix="/api/vehicles-dashboard", tags=["vehicles"])


# ─────────────────────────── Helpers ────────────────────────────────────────

def _current_month_range():
    """Return (first_day, last_day) of the current calendar month."""
    today = date.today()
    first = today.replace(day=1)
    if today.month == 12:
        last = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return first, last


def _parse_date(value: Optional[str], fallback: date) -> date:
    """Parse ISO date string; return fallback on any parse error."""
    if not value:
        return fallback
    try:
        return date.fromisoformat(value[:10])
    except Exception:
        return fallback


def _visibility_filter(user: User):
    """
    Returns a SQLAlchemy WHERE clause for Vehicle multi-tenancy (D-06).
    Returns None when user has global visibility (superadmin / account_owner).
    """
    org_ids = get_org_filter(user)
    if org_ids is None:
        return None
    return or_(
        Vehicle.owner_org_id.in_(org_ids),
        Vehicle.assigned_org_id.in_(org_ids),
    )


def _apply_visibility(q, user: User):
    """Apply visibility filter to a query that selects from vehicles."""
    clause = _visibility_filter(user)
    if clause is not None:
        q = q.where(clause)
    return q


# ─────────────────────────── 1. KPI cards ────────────────────────────────────

@router.get("/kpi")
async def kpi_summary(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    owner_org_ids: Optional[str] = Query(None, description="Comma-separated org ids"),
    region: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    KPI cards:
      total_vehicles     — count of visible vehicles (optional org filter)
      fuel_total_cost    — SUM(total_amount OR liters*price_per_liter) for period
      repairs_total_cost — SUM(COALESCE(purchase.contract_price, repair.cost_amount))
      total_mileage_km   — SUM per vehicle of (MAX - MIN odometer) for period
    """
    first, last = _current_month_range()
    d_from = _parse_date(date_from, first)
    d_to = _parse_date(date_to, last)

    # Optional additional org filter (on top of visibility)
    extra_org_ids: Optional[List[int]] = None
    if owner_org_ids:
        try:
            extra_org_ids = [int(x.strip()) for x in owner_org_ids.split(",") if x.strip()]
        except ValueError:
            extra_org_ids = None

    # ── total_vehicles ──
    vq = select(func.count(Vehicle.id))
    vq = _apply_visibility(vq, current_user)
    if extra_org_ids:
        vq = vq.where(Vehicle.owner_org_id.in_(extra_org_ids))
    total_vehicles = (await db.execute(vq)).scalar() or 0

    # ── fuel_total_cost ──
    # COALESCE(total_amount, liters * price_per_liter)
    fuel_amount_expr = func.coalesce(
        FuelLog.total_amount,
        FuelLog.liters * FuelLog.price_per_liter,
    )
    fq = (
        select(func.coalesce(func.sum(fuel_amount_expr), 0))
        .join(Vehicle, FuelLog.vehicle_id == Vehicle.id)
        .where(FuelLog.date >= d_from, FuelLog.date <= d_to)
    )
    fq = _apply_visibility(fq, current_user)
    if extra_org_ids:
        fq = fq.where(Vehicle.owner_org_id.in_(extra_org_ids))
    fuel_total_cost = float((await db.execute(fq)).scalar() or 0)

    # ── repairs_total_cost — D-18: prefer linked Purchase.contract_price ──
    # Import here to avoid circular; Purchase is already imported in other routers
    from app.models.purchase import Purchase as PurchaseModel
    rq = (
        select(
            func.coalesce(
                func.sum(
                    func.coalesce(PurchaseModel.contract_price, VehicleRepair.cost_amount, 0)
                ),
                0,
            )
        )
        .select_from(VehicleRepair)
        .outerjoin(PurchaseModel, PurchaseModel.id == VehicleRepair.purchase_id)
        .join(Vehicle, Vehicle.id == VehicleRepair.vehicle_id)
        .where(VehicleRepair.date >= d_from, VehicleRepair.date <= d_to)
    )
    rq = _apply_visibility(rq, current_user)
    if extra_org_ids:
        rq = rq.where(Vehicle.owner_org_id.in_(extra_org_ids))
    repairs_total_cost = float((await db.execute(rq)).scalar() or 0)

    # ── total_mileage_km — SUM(MAX-MIN) per vehicle for period ──
    from app.models.vehicle_odometer import VehicleOdometer
    vis_ids_q = select(Vehicle.id)
    vis_ids_q = _apply_visibility(vis_ids_q, current_user)
    if extra_org_ids:
        vis_ids_q = vis_ids_q.where(Vehicle.owner_org_id.in_(extra_org_ids))
    vis_ids = [r[0] for r in (await db.execute(vis_ids_q)).all()]

    total_mileage_km = 0
    if vis_ids:
        mileage_q = (
            select(
                VehicleOdometer.vehicle_id,
                (func.max(VehicleOdometer.odometer_km) - func.min(VehicleOdometer.odometer_km)).label("delta"),
            )
            .where(
                VehicleOdometer.vehicle_id.in_(vis_ids),
                VehicleOdometer.date >= d_from,
                VehicleOdometer.date <= d_to,
            )
            .group_by(VehicleOdometer.vehicle_id)
        )
        rows = (await db.execute(mileage_q)).all()
        total_mileage_km = sum(r.delta or 0 for r in rows)

    return {
        "total_vehicles": total_vehicles,
        "fuel_total_cost": round(fuel_total_cost, 2),
        "repairs_total_cost": round(repairs_total_cost, 2),
        "total_mileage_km": int(total_mileage_km),
        "period": {"from": d_from.isoformat(), "to": d_to.isoformat()},
    }


# ─────────────────────────── 2. Fuel canister widget ─────────────────────────

@router.get("/fuel-canister")
async def fuel_canister(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    fuel_budget: Optional[float] = Query(None, description="User-defined budget (RUB)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    SVG canister widget data.
    level = (fuel_budget - spent_amount) / fuel_budget (0..1, 0 if overspent).
    If fuel_budget not provided, defaults to 1.5 × previous period spend.
    """
    first, last = _current_month_range()
    d_from = _parse_date(date_from, first)
    d_to = _parse_date(date_to, last)

    fuel_expr = func.coalesce(
        FuelLog.total_amount,
        FuelLog.liters * FuelLog.price_per_liter,
    )

    def _fuel_q(from_d: date, to_d: date):
        q = (
            select(
                func.coalesce(func.sum(FuelLog.liters), 0).label("liters"),
                func.coalesce(func.sum(fuel_expr), 0).label("amount"),
            )
            .join(Vehicle, FuelLog.vehicle_id == Vehicle.id)
            .where(FuelLog.date >= from_d, FuelLog.date <= to_d)
        )
        return _apply_visibility(q, current_user)

    row = (await db.execute(_fuel_q(d_from, d_to))).one()
    spent_l = float(row.liters or 0)
    spent_amount = float(row.amount or 0)

    if fuel_budget is None or fuel_budget <= 0:
        # Previous period: same duration
        period_len = (d_to - d_from).days + 1
        prev_from = d_from - timedelta(days=period_len)
        prev_to = d_from - timedelta(days=1)
        prev_row = (await db.execute(_fuel_q(prev_from, prev_to))).one()
        prev_spend = float(prev_row.amount or 0)
        fuel_budget = prev_spend * 1.5 if prev_spend > 0 else 0

    if fuel_budget <= 0:
        level = 0.5
    else:
        remaining = fuel_budget - spent_amount
        level = max(0.0, min(1.0, remaining / fuel_budget))

    period_label = f"{d_from.strftime('%d.%m')} — {d_to.strftime('%d.%m.%Y')}"

    return {
        "spent_l": round(spent_l, 2),
        "spent_amount": round(spent_amount, 2),
        "fuel_budget": round(fuel_budget, 2),
        "level": round(level, 4),
        "period_label": period_label,
    }


# ─────────────────────────── 3. In-repair list ───────────────────────────────

@router.get("/in-repair")
async def in_repair(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    List vehicles that have an open repair (status IN planned / in_progress).
    Returns first photo attachment id for each vehicle.
    """
    # Subquery: open repair per vehicle (latest)
    open_repair_sq = (
        select(
            VehicleRepair.vehicle_id,
            VehicleRepair.id.label("repair_id"),
            VehicleRepair.status.label("repair_status"),
            VehicleRepair.description.label("repair_description"),
            VehicleRepair.mileage_at_repair,
            VehicleRepair.date.label("repair_date"),
        )
        .where(VehicleRepair.status.in_(["planned", "in_progress"]))
        .distinct(VehicleRepair.vehicle_id)
        .order_by(VehicleRepair.vehicle_id, VehicleRepair.id.desc())
    ).subquery("open_repair")

    # Subquery: first photo attachment per vehicle
    photo_sq = (
        select(
            VehicleAttachment.vehicle_id,
            func.min(VehicleAttachment.id).label("photo_attachment_id"),
        )
        .where(VehicleAttachment.kind == "photo")
        .group_by(VehicleAttachment.vehicle_id)
    ).subquery("photo_attach")

    q = (
        select(
            Vehicle.id,
            Vehicle.brand,
            Vehicle.model,
            Vehicle.plate,
            open_repair_sq.c.repair_id,
            open_repair_sq.c.repair_status,
            open_repair_sq.c.repair_description,
            open_repair_sq.c.mileage_at_repair,
            open_repair_sq.c.repair_date,
            photo_sq.c.photo_attachment_id,
        )
        .join(open_repair_sq, open_repair_sq.c.vehicle_id == Vehicle.id)
        .outerjoin(photo_sq, photo_sq.c.vehicle_id == Vehicle.id)
    )
    q = _apply_visibility(q, current_user)

    rows = (await db.execute(q)).all()

    return [
        {
            "vehicle_id": r.id,
            "brand": r.brand,
            "model": r.model,
            "plate": r.plate,
            "photo_attachment_id": r.photo_attachment_id,
            "repair_id": r.repair_id,
            "repair_status": r.repair_status,
            "repair_description": r.repair_description,
            "mileage_at_repair": r.mileage_at_repair,
            "repair_date": r.repair_date.isoformat() if r.repair_date else None,
            "expected_finish_date": None,  # nullable per plan — no column in model yet
        }
        for r in rows
    ]


# ─────────────────────────── 4. Maintenance warnings ─────────────────────────

@router.get("/maintenance-warning")
async def maintenance_warning(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Vehicles requiring attention. Warning types:
    - TO_SOON:      (next_to_km - current_odometer_km) < 1000
    - OSAGO_EXPIRY: insurance_until < today + 30 days
    - LICENSE_EXPIRY: driver with license_expires_at < today (trips last 30 days)
    - MED_CERT_EXPIRY: driver with medical_cert_expires_at < today (trips last 30 days)

    Results sorted by urgency (min days_left / km_left first).
    """
    today = date.today()
    horizon = today + timedelta(days=30)
    trip_since = today - timedelta(days=30)

    warnings = []

    # ── TO_SOON ──
    to_q = (
        select(Vehicle.id, Vehicle.brand, Vehicle.model, Vehicle.plate,
               Vehicle.next_to_km, Vehicle.current_odometer_km)
        .where(
            Vehicle.next_to_km.is_not(None),
            Vehicle.current_odometer_km.is_not(None),
            (Vehicle.next_to_km - Vehicle.current_odometer_km) < 1000,
        )
    )
    to_q = _apply_visibility(to_q, current_user)
    for r in (await db.execute(to_q)).all():
        km_left = (r.next_to_km or 0) - (r.current_odometer_km or 0)
        warnings.append({
            "vehicle_id": r.id,
            "brand": r.brand,
            "model": r.model,
            "plate": r.plate,
            "warning_type": "TO_SOON",
            "days_left": None,
            "km_left": int(km_left),
        })

    # ── OSAGO_EXPIRY ──
    ins_q = (
        select(Vehicle.id, Vehicle.brand, Vehicle.model, Vehicle.plate, Vehicle.insurance_until)
        .where(
            Vehicle.insurance_until.is_not(None),
            Vehicle.insurance_until <= horizon,
        )
    )
    ins_q = _apply_visibility(ins_q, current_user)
    for r in (await db.execute(ins_q)).all():
        days_left = (r.insurance_until - today).days
        warnings.append({
            "vehicle_id": r.id,
            "brand": r.brand,
            "model": r.model,
            "plate": r.plate,
            "warning_type": "OSAGO_EXPIRY",
            "days_left": int(days_left),
            "km_left": None,
        })

    # ── LICENSE_EXPIRY & MED_CERT_EXPIRY — User drivers in recent trips ──
    user_trips_q = (
        select(
            Vehicle.id.label("vehicle_id"),
            Vehicle.brand,
            Vehicle.model,
            Vehicle.plate,
            User.license_expires_at,
            User.medical_cert_expires_at,
        )
        .select_from(Trip)
        .join(Vehicle, Vehicle.id == Trip.vehicle_id)
        .join(User, User.id == Trip.driver_user_id)
        .where(
            Trip.date >= trip_since,
            Trip.driver_user_id.is_not(None),
            or_(
                and_(User.license_expires_at.is_not(None), User.license_expires_at <= horizon),
                and_(User.medical_cert_expires_at.is_not(None), User.medical_cert_expires_at <= horizon),
            ),
        )
        .distinct()
    )
    user_trips_q = _apply_visibility(user_trips_q, current_user)
    for r in (await db.execute(user_trips_q)).all():
        if r.license_expires_at and r.license_expires_at <= horizon:
            days_left = (r.license_expires_at - today).days
            warnings.append({
                "vehicle_id": r.vehicle_id,
                "brand": r.brand,
                "model": r.model,
                "plate": r.plate,
                "warning_type": "LICENSE_EXPIRY",
                "days_left": int(days_left),
                "km_left": None,
            })
        if r.medical_cert_expires_at and r.medical_cert_expires_at <= horizon:
            days_left = (r.medical_cert_expires_at - today).days
            warnings.append({
                "vehicle_id": r.vehicle_id,
                "brand": r.brand,
                "model": r.model,
                "plate": r.plate,
                "warning_type": "MED_CERT_EXPIRY",
                "days_left": int(days_left),
                "km_left": None,
            })

    # ── External driver warnings ──
    ext_trips_q = (
        select(
            Vehicle.id.label("vehicle_id"),
            Vehicle.brand,
            Vehicle.model,
            Vehicle.plate,
            ExternalDriver.license_expires_at,
            ExternalDriver.medical_cert_expires_at,
        )
        .select_from(Trip)
        .join(Vehicle, Vehicle.id == Trip.vehicle_id)
        .join(ExternalDriver, ExternalDriver.id == Trip.driver_external_id)
        .where(
            Trip.date >= trip_since,
            Trip.driver_external_id.is_not(None),
            or_(
                and_(ExternalDriver.license_expires_at.is_not(None), ExternalDriver.license_expires_at <= horizon),
                and_(ExternalDriver.medical_cert_expires_at.is_not(None), ExternalDriver.medical_cert_expires_at <= horizon),
            ),
        )
        .distinct()
    )
    ext_trips_q = _apply_visibility(ext_trips_q, current_user)
    for r in (await db.execute(ext_trips_q)).all():
        if r.license_expires_at and r.license_expires_at <= horizon:
            days_left = (r.license_expires_at - today).days
            warnings.append({
                "vehicle_id": r.vehicle_id,
                "brand": r.brand,
                "model": r.model,
                "plate": r.plate,
                "warning_type": "LICENSE_EXPIRY",
                "days_left": int(days_left),
                "km_left": None,
            })
        if r.medical_cert_expires_at and r.medical_cert_expires_at <= horizon:
            days_left = (r.medical_cert_expires_at - today).days
            warnings.append({
                "vehicle_id": r.vehicle_id,
                "brand": r.brand,
                "model": r.model,
                "plate": r.plate,
                "warning_type": "MED_CERT_EXPIRY",
                "days_left": int(days_left),
                "km_left": None,
            })

    # Sort by urgency: km_left and days_left, smaller = more urgent; None values last
    def _urgency_key(w):
        d = w["days_left"] if w["days_left"] is not None else 9999
        k = w["km_left"] if w["km_left"] is not None else 9999
        return min(d, k)

    warnings.sort(key=_urgency_key)
    return warnings


# ─────────────────────────── 5. By-org bar chart ─────────────────────────────

@router.get("/by-org")
async def by_org(
    mode: str = Query("owner", description="owner | assigned"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Bar chart: vehicle count grouped by owner_org or assigned_org."""
    org_col = Vehicle.owner_org_id if mode != "assigned" else Vehicle.assigned_org_id

    q = (
        select(
            org_col.label("org_id"),
            Organization.name.label("org_name"),
            func.count(Vehicle.id).label("count"),
        )
        .join(Organization, Organization.id == org_col)
        .where(org_col.is_not(None))
        .group_by(org_col, Organization.name)
        .order_by(func.count(Vehicle.id).desc())
    )
    q = _apply_visibility(q, current_user)

    rows = (await db.execute(q)).all()
    return [
        {"org_id": r.org_id, "org_name": r.org_name, "count": r.count}
        for r in rows
    ]


# ─────────────────────────── 6. Fuel by period (line chart) ──────────────────

@router.get("/fuel-by-period")
async def fuel_by_period(
    granularity: str = Query("day", description="day | week | month | year"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Line chart: fuel cost/liters grouped by time period (PostgreSQL date_trunc)."""
    first, last = _current_month_range()
    d_from = _parse_date(date_from, first)
    d_to = _parse_date(date_to, last)

    # Validate granularity to avoid SQL injection
    allowed = {"day", "week", "month", "year"}
    if granularity not in allowed:
        granularity = "day"

    fuel_expr = func.coalesce(
        FuelLog.total_amount,
        FuelLog.liters * FuelLog.price_per_liter,
    )

    period_col = func.date_trunc(granularity, FuelLog.date).label("period")

    q = (
        select(
            period_col,
            func.coalesce(func.sum(FuelLog.liters), 0).label("total_liters"),
            func.coalesce(func.sum(fuel_expr), 0).label("total_amount"),
        )
        .join(Vehicle, FuelLog.vehicle_id == Vehicle.id)
        .where(FuelLog.date >= d_from, FuelLog.date <= d_to)
        .group_by(period_col)
        .order_by(period_col)
    )
    q = _apply_visibility(q, current_user)

    rows = (await db.execute(q)).all()
    return [
        {
            "period": r.period.date().isoformat() if hasattr(r.period, "date") else str(r.period)[:10],
            "total_liters": float(r.total_liters or 0),
            "total_amount": float(r.total_amount or 0),
        }
        for r in rows
    ]


# ─────────────────────────── 7. State donut chart ────────────────────────────

# Color mapping for known VehicleState values
_STATE_COLORS = {
    "working": "#22c55e",      # green
    "broken": "#ef4444",       # red
    "in_repair": "#f97316",    # orange
    "needs_repair": "#eab308", # yellow
    "destroyed": "#6b7280",    # gray
    "utilized": "#a855f7",     # purple
}

_STATE_LABELS = {
    "working": "Работает",
    "broken": "Сломан",
    "in_repair": "В ремонте",
    "needs_repair": "Требует ремонта",
    "destroyed": "Уничтожен",
    "utilized": "Утилизирован",
}


@router.get("/state-donut")
async def state_donut(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Donut chart: vehicle count by state with label and color."""
    q = (
        select(
            Vehicle.state,
            func.count(Vehicle.id).label("count"),
        )
        .group_by(Vehicle.state)
        .order_by(func.count(Vehicle.id).desc())
    )
    q = _apply_visibility(q, current_user)

    rows = (await db.execute(q)).all()
    return [
        {
            "state": r.state or "unknown",
            "label": _STATE_LABELS.get(r.state or "", r.state or "Неизвестно"),
            "count": r.count,
            "color": _STATE_COLORS.get(r.state or "", "#94a3b8"),
        }
        for r in rows
    ]


# ─────────────────────────── 8. Top expenses table ───────────────────────────

@router.get("/top-expenses")
async def top_expenses(
    limit: int = Query(10, ge=1, le=100),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    TOP-N vehicles by total expenses (fuel + repair) for the period.
    Repair cost: COALESCE(linked Purchase.contract_price, VehicleRepair.cost_amount).
    Returns breakdown: fuel_cost, repair_cost, total_cost.
    """
    first, last = _current_month_range()
    # Default: last 90 days if no date provided
    default_from = date.today() - timedelta(days=89)
    d_from = _parse_date(date_from, default_from)
    d_to = _parse_date(date_to, last)

    from app.models.purchase import Purchase as PurchaseModel

    fuel_expr = func.coalesce(
        FuelLog.total_amount,
        FuelLog.liters * FuelLog.price_per_liter,
    )

    # Fuel aggregation per vehicle
    fuel_sq = (
        select(
            FuelLog.vehicle_id,
            func.coalesce(func.sum(fuel_expr), 0).label("fuel_cost"),
        )
        .where(FuelLog.date >= d_from, FuelLog.date <= d_to)
        .group_by(FuelLog.vehicle_id)
    ).subquery("fuel_agg")

    # Repair aggregation per vehicle (D-18: prefer purchase price)
    repair_sq = (
        select(
            VehicleRepair.vehicle_id,
            func.coalesce(
                func.sum(
                    func.coalesce(PurchaseModel.contract_price, VehicleRepair.cost_amount, 0)
                ),
                0,
            ).label("repair_cost"),
        )
        .select_from(VehicleRepair)
        .outerjoin(PurchaseModel, PurchaseModel.id == VehicleRepair.purchase_id)
        .where(VehicleRepair.date >= d_from, VehicleRepair.date <= d_to)
        .group_by(VehicleRepair.vehicle_id)
    ).subquery("repair_agg")

    q = (
        select(
            Vehicle.id,
            Vehicle.plate,
            Vehicle.brand,
            Vehicle.model,
            func.coalesce(fuel_sq.c.fuel_cost, 0).label("fuel_cost"),
            func.coalesce(repair_sq.c.repair_cost, 0).label("repair_cost"),
            (
                func.coalesce(fuel_sq.c.fuel_cost, 0)
                + func.coalesce(repair_sq.c.repair_cost, 0)
            ).label("total_cost"),
        )
        .outerjoin(fuel_sq, fuel_sq.c.vehicle_id == Vehicle.id)
        .outerjoin(repair_sq, repair_sq.c.vehicle_id == Vehicle.id)
        .where(
            or_(
                fuel_sq.c.fuel_cost.is_not(None),
                repair_sq.c.repair_cost.is_not(None),
            )
        )
        .order_by(
            (
                func.coalesce(fuel_sq.c.fuel_cost, 0)
                + func.coalesce(repair_sq.c.repair_cost, 0)
            ).desc()
        )
        .limit(limit)
    )
    q = _apply_visibility(q, current_user)

    rows = (await db.execute(q)).all()
    return [
        {
            "vehicle_id": r.id,
            "plate": r.plate,
            "brand_model": f"{r.brand or ''} {r.model or ''}".strip() or r.plate,
            "fuel_cost": float(r.fuel_cost or 0),
            "repair_cost": float(r.repair_cost or 0),
            "total_cost": float(r.total_cost or 0),
        }
        for r in rows
    ]


# ─────────────────────────── 9. Drill-down endpoint ──────────────────────────

def _vehicle_item(r, fuel_cost: float = 0.0, repair_cost: float = 0.0) -> dict:
    return {
        "vehicle_id": r.id,
        "plate": r.plate or "",
        "brand": r.brand or "",
        "model": r.model or "",
        "brand_model": f"{r.brand or ''} {r.model or ''}".strip() or (r.plate or ""),
        "state": r.state or "unknown",
        "owner_org_name": r.owner_org_name if hasattr(r, "owner_org_name") else "",
        "fuel_cost": round(fuel_cost, 2),
        "repair_cost": round(repair_cost, 2),
    }


@router.get("/drill")
async def drill_vehicles(
    dimension: str = Query(..., description="bar_org | donut_state | line_fuel | top_expenses"),
    value: str = Query(..., description="Dimension value to drill into"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Return list of vehicles matching the clicked dimension+value."""
    first, last = _current_month_range()
    d_from = _parse_date(date_from, first)
    d_to = _parse_date(date_to, last)

    from app.models.purchase import Purchase as PurchaseModel

    OwnerOrg = Organization.__table__.alias("owner_org")

    base_q = (
        select(
            Vehicle.id,
            Vehicle.plate,
            Vehicle.brand,
            Vehicle.model,
            Vehicle.state,
            Vehicle.owner_org_id,
        )
    )
    base_q = _apply_visibility(base_q, current_user)

    items: list[dict] = []

    if dimension == "bar_org":
        # value = org_name → vehicles WHERE owner org name = value
        q = (
            base_q
            .join(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(Organization.name.label("owner_org_name"))
            .where(Organization.name == value)
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r) for r in rows]

    elif dimension == "donut_state":
        # value = label → find internal state key
        reverse_labels = {v: k for k, v in _STATE_LABELS.items()}
        state_key = reverse_labels.get(value, value)
        q = (
            base_q
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(Organization.name.label("owner_org_name"))
            .where(Vehicle.state == state_key)
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r) for r in rows]

    elif dimension == "line_fuel":
        # value = YYYY-MM-DD → vehicles that have a fuel log on that date
        fuel_date = _parse_date(value, d_from)
        fuel_sq = (
            select(FuelLog.vehicle_id)
            .where(FuelLog.date == fuel_date)
            .distinct()
        ).subquery("fuel_date_veh")
        fuel_amount_expr = func.coalesce(
            FuelLog.total_amount, FuelLog.liters * FuelLog.price_per_liter
        )
        fuel_agg_sq = (
            select(
                FuelLog.vehicle_id,
                func.coalesce(func.sum(fuel_amount_expr), 0).label("fuel_cost"),
            )
            .where(FuelLog.date == fuel_date)
            .group_by(FuelLog.vehicle_id)
        ).subquery("fuel_agg_drill")
        q = (
            base_q
            .join(fuel_sq, fuel_sq.c.vehicle_id == Vehicle.id)
            .outerjoin(fuel_agg_sq, fuel_agg_sq.c.vehicle_id == Vehicle.id)
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(
                Organization.name.label("owner_org_name"),
                func.coalesce(fuel_agg_sq.c.fuel_cost, 0).label("fuel_cost"),
            )
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r, fuel_cost=float(r.fuel_cost or 0)) for r in rows]

    elif dimension == "top_expenses":
        # value = vehicle_id string → single vehicle + expense breakdown
        try:
            vid = int(value)
        except ValueError:
            return {"items": [], "total": 0, "dimension": dimension, "value": value}
        fuel_amount_expr = func.coalesce(
            FuelLog.total_amount, FuelLog.liters * FuelLog.price_per_liter
        )
        fuel_agg_sq = (
            select(
                FuelLog.vehicle_id,
                func.coalesce(func.sum(fuel_amount_expr), 0).label("fuel_cost"),
            )
            .where(FuelLog.date >= d_from, FuelLog.date <= d_to)
            .group_by(FuelLog.vehicle_id)
        ).subquery("fuel_agg_te")
        repair_agg_sq = (
            select(
                VehicleRepair.vehicle_id,
                func.coalesce(
                    func.sum(func.coalesce(PurchaseModel.contract_price, VehicleRepair.cost_amount, 0)), 0
                ).label("repair_cost"),
            )
            .select_from(VehicleRepair)
            .outerjoin(PurchaseModel, PurchaseModel.id == VehicleRepair.purchase_id)
            .where(VehicleRepair.date >= d_from, VehicleRepair.date <= d_to)
            .group_by(VehicleRepair.vehicle_id)
        ).subquery("repair_agg_te")
        q = (
            base_q
            .outerjoin(fuel_agg_sq, fuel_agg_sq.c.vehicle_id == Vehicle.id)
            .outerjoin(repair_agg_sq, repair_agg_sq.c.vehicle_id == Vehicle.id)
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(
                Organization.name.label("owner_org_name"),
                func.coalesce(fuel_agg_sq.c.fuel_cost, 0).label("fuel_cost"),
                func.coalesce(repair_agg_sq.c.repair_cost, 0).label("repair_cost"),
            )
            .where(Vehicle.id == vid)
        )
        rows = (await db.execute(q)).all()
        items = [
            _vehicle_item(r, fuel_cost=float(r.fuel_cost or 0), repair_cost=float(r.repair_cost or 0))
            for r in rows
        ]

    else:
        return {"items": [], "total": 0, "dimension": dimension, "value": value}

    return {"items": items, "total": len(items), "dimension": dimension, "value": value}


# ─────────────────────────── 10. All vehicles summary table ──────────────────

@router.get("/all-vehicles-summary")
async def all_vehicles_summary(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    owner_org_ids: Optional[str] = Query(None, description="Comma-separated org ids"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Full vehicles table with aggregated fuel cost, repair cost, mileage for the period.
    No LIMIT — returns all visible vehicles.
    """
    first, last = _current_month_range()
    d_from = _parse_date(date_from, first)
    d_to = _parse_date(date_to, last)

    extra_org_ids: Optional[List[int]] = None
    if owner_org_ids:
        try:
            extra_org_ids = [int(x.strip()) for x in owner_org_ids.split(",") if x.strip()]
        except ValueError:
            extra_org_ids = None

    from app.models.purchase import Purchase as PurchaseModel
    from app.models.vehicle_odometer import VehicleOdometer

    fuel_expr = func.coalesce(FuelLog.total_amount, FuelLog.liters * FuelLog.price_per_liter)

    fuel_sq = (
        select(
            FuelLog.vehicle_id,
            func.coalesce(func.sum(fuel_expr), 0).label("fuel_cost"),
        )
        .where(FuelLog.date >= d_from, FuelLog.date <= d_to)
        .group_by(FuelLog.vehicle_id)
    ).subquery("all_veh_fuel")

    repair_sq = (
        select(
            VehicleRepair.vehicle_id,
            func.coalesce(
                func.sum(func.coalesce(PurchaseModel.contract_price, VehicleRepair.cost_amount, 0)), 0
            ).label("repair_cost"),
        )
        .select_from(VehicleRepair)
        .outerjoin(PurchaseModel, PurchaseModel.id == VehicleRepair.purchase_id)
        .where(VehicleRepair.date >= d_from, VehicleRepair.date <= d_to)
        .group_by(VehicleRepair.vehicle_id)
    ).subquery("all_veh_repair")

    mileage_sq = (
        select(
            VehicleOdometer.vehicle_id,
            (func.max(VehicleOdometer.odometer_km) - func.min(VehicleOdometer.odometer_km)).label("mileage_km"),
        )
        .where(VehicleOdometer.date >= d_from, VehicleOdometer.date <= d_to)
        .group_by(VehicleOdometer.vehicle_id)
    ).subquery("all_veh_mileage")

    today = date.today()
    horizon_30 = today + timedelta(days=30)

    q = (
        select(
            Vehicle.id,
            Vehicle.plate,
            Vehicle.brand,
            Vehicle.model,
            Vehicle.state,
            Vehicle.insurance_until,
            Organization.name.label("owner_org_name"),
            func.coalesce(fuel_sq.c.fuel_cost, 0).label("fuel_cost"),
            func.coalesce(repair_sq.c.repair_cost, 0).label("repair_cost"),
            func.coalesce(mileage_sq.c.mileage_km, 0).label("mileage_km"),
        )
        .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
        .outerjoin(fuel_sq, fuel_sq.c.vehicle_id == Vehicle.id)
        .outerjoin(repair_sq, repair_sq.c.vehicle_id == Vehicle.id)
        .outerjoin(mileage_sq, mileage_sq.c.vehicle_id == Vehicle.id)
        .order_by(Vehicle.plate)
    )
    q = _apply_visibility(q, current_user)
    if extra_org_ids:
        q = q.where(Vehicle.owner_org_id.in_(extra_org_ids))

    rows = (await db.execute(q)).all()
    return [
        {
            "vehicle_id": r.id,
            "plate": r.plate or "",
            "brand_model": f"{r.brand or ''} {r.model or ''}".strip() or (r.plate or ""),
            "state": r.state or "unknown",
            "owner_org_name": r.owner_org_name or "",
            "fuel_cost": float(r.fuel_cost or 0),
            "repair_cost": float(r.repair_cost or 0),
            "mileage_km": int(r.mileage_km or 0),
            "insurance_overdue": (
                r.insurance_until is not None and r.insurance_until < today
            ),
            "insurance_until": r.insurance_until.isoformat() if r.insurance_until else None,
        }
        for r in rows
    ]


# ─────────────────────────── 11. By-region (Phase 29.1) ──────────────────────

@router.get("/by-region")
async def by_region(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Phase 29.1: Fleet geography — group vehicles by assigned_text (region string).
    Returns list sorted by count desc.
    If fewer than 5 vehicles visible, adds mock_demo flag.
    """
    from sqlalchemy import bindparam as _bindparam
    _unspec = _bindparam('unspec_region', "Не указан", literal_execute=True)
    _region_expr = func.coalesce(Vehicle.assigned_text, _unspec)
    q = (
        select(
            _region_expr.label("region"),
            Vehicle.state,
            func.count(Vehicle.id).label("cnt"),
        )
        .group_by(_region_expr, Vehicle.state)
        .order_by(func.count(Vehicle.id).desc())
    )
    q = _apply_visibility(q, current_user)
    rows = (await db.execute(q)).all()

    # Aggregate by region
    region_map: dict = {}
    for r in rows:
        rg = r.region
        if rg not in region_map:
            region_map[rg] = {"region": rg, "count": 0, "by_state": {}}
        region_map[rg]["count"] += r.cnt
        state_key = r.state or "unknown"
        region_map[rg]["by_state"][state_key] = region_map[rg]["by_state"].get(state_key, 0) + r.cnt

    result = sorted(region_map.values(), key=lambda x: x["count"], reverse=True)

    # штаб_label heuristic — map common region strings
    _SHTAB = {
        "Ростов-на-Дону": "штаб РНД, СТО",
        "ЦУ Москва": "штаб ЦУ",
        "Луганск": "ФПГ ЛНР",
        "Донецк": "ФПГ ДНР",
        "Запорожье": "ФПГ Запорожье",
        "Иркутск": "ФПГ Иркутск",
    }
    for item in result:
        item["shtab_label"] = _SHTAB.get(item["region"], "")

    total = sum(item["count"] for item in result)
    mock_demo = total < 5

    return {"items": result, "mock_demo": mock_demo}


# ─────────────────────────── 12. Driver reports feed (Phase 29.1 / 30) ───────

@router.get("/driver-reports")
async def driver_reports(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Phase 29.1: Feed of recent events for Driver Reports panel.
    Phase 30 (mobile app) will populate this with real driver checklist submissions.
    Currently sources from: VehicleOdometer (last updates) + VehicleRepair (recent).
    Returns [] when empty — UI shows placeholder message.
    """
    from app.models.vehicle_odometer import VehicleOdometer

    feed: list[dict] = []

    # Recent odometer updates
    odo_q = (
        select(
            VehicleOdometer.vehicle_id,
            VehicleOdometer.odometer_km,
            VehicleOdometer.date,
            Vehicle.plate,
            Vehicle.brand,
            Vehicle.model,
        )
        .join(Vehicle, Vehicle.id == VehicleOdometer.vehicle_id)
        .order_by(VehicleOdometer.created_at.desc())
        .limit(limit)
    )
    odo_q = _apply_visibility(odo_q, current_user)
    try:
        odo_rows = (await db.execute(odo_q)).all()
        for r in odo_rows:
            feed.append({
                "vehicle_id": r.vehicle_id,
                "plate": r.plate or "",
                "type": "odometer_update",
                "ic": "ok",
                "title": f"Пробег обновлён: {r.odometer_km:,} км".replace(",", "\u00a0"),
                "author": "",
                "timestamp": r.date.isoformat() if r.date else "",
            })
    except Exception:
        pass

    # Recent repair requests
    rep_q = (
        select(
            VehicleRepair.vehicle_id,
            VehicleRepair.description,
            VehicleRepair.date,
            Vehicle.plate,
            Vehicle.brand,
            Vehicle.model,
        )
        .join(Vehicle, Vehicle.id == VehicleRepair.vehicle_id)
        .order_by(VehicleRepair.created_at.desc())
        .limit(limit)
    )
    rep_q = _apply_visibility(rep_q, current_user)
    try:
        rep_rows = (await db.execute(rep_q)).all()
        for r in rep_rows:
            feed.append({
                "vehicle_id": r.vehicle_id,
                "plate": r.plate or "",
                "type": "issue",
                "ic": "alert",
                "title": r.description or "Заявка на ремонт",
                "author": "",
                "timestamp": r.date.isoformat() if r.date else "",
            })
    except Exception:
        pass

    # Sort by timestamp desc, take top limit
    feed.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return feed[:limit]


# ─────────────────────────── 13. Filter counts (Phase 29.1) ──────────────────

@router.get("/filter-counts")
async def filter_counts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Phase 29.1: Counts for filter chips in VehicleDashboardView.
    Returns: all, working, in_repair, not_running, no_report_30d, for_disposal.
    """
    from app.models.vehicle_odometer import VehicleOdometer

    today = date.today()
    cutoff_30d = today - timedelta(days=30)

    # All vehicles count
    all_q = select(func.count(Vehicle.id))
    all_q = _apply_visibility(all_q, current_user)
    total_all = int((await db.execute(all_q)).scalar() or 0)

    # By state counts
    state_q = (
        select(Vehicle.state, func.count(Vehicle.id).label("cnt"))
        .group_by(Vehicle.state)
    )
    state_q = _apply_visibility(state_q, current_user)
    state_rows = (await db.execute(state_q)).all()
    state_map = {r.state: r.cnt for r in state_rows}

    working = state_map.get("working", 0)
    in_repair = state_map.get("in_repair", 0) + state_map.get("broken", 0)
    not_running = (
        state_map.get("destroyed", 0)
        + state_map.get("utilized", 0)
        + state_map.get("needs_repair", 0)
    )

    # No report in 30d: working vehicles with NO odometer record in last 30 days
    recent_odo_sq = (
        select(VehicleOdometer.vehicle_id)
        .where(VehicleOdometer.date >= cutoff_30d)
        .distinct()
    ).subquery("recent_odo")

    no_report_q = (
        select(func.count(Vehicle.id))
        .outerjoin(recent_odo_sq, recent_odo_sq.c.vehicle_id == Vehicle.id)
        .where(recent_odo_sq.c.vehicle_id.is_(None))
        .where(Vehicle.state == "working")
    )
    no_report_q = _apply_visibility(no_report_q, current_user)
    no_report_30d = int((await db.execute(no_report_q)).scalar() or 0)

    # For disposal: destroyed + utilized
    for_disposal = state_map.get("destroyed", 0) + state_map.get("utilized", 0)

    return {
        "all": total_all,
        "working": working,
        "in_repair": in_repair,
        "not_running": not_running,
        "no_report_30d": no_report_30d,
        "for_disposal": for_disposal,
        "mock_demo": total_all < 5,
    }
