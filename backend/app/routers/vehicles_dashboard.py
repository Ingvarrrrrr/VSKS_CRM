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
