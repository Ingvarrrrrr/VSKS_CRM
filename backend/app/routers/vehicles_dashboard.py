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
from sqlalchemy import select, func, or_, and_, text
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
from app.models.vehicle_transfer_history import VehicleTransferHistory

router = APIRouter(prefix="/api/vehicles-dashboard", tags=["vehicles"])


@router.get("/transfer-history-recent")
async def transfer_history_recent(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Phase 30 PR2: глобальный список последних передач ТС между штабами.
    Используется в /fleet/regions журнале передач."""
    res = await db.execute(
        select(VehicleTransferHistory).order_by(VehicleTransferHistory.changed_at.desc()).limit(limit)
    )
    rows = res.scalars().all()
    # Resolve org names + vehicle plate
    out = []
    for r in rows:
        veh = await db.get(Vehicle, r.vehicle_id) if r.vehicle_id else None
        from_org = await db.get(Organization, r.from_assigned_org_id or r.from_owner_org_id) if (r.from_assigned_org_id or r.from_owner_org_id) else None
        to_org = await db.get(Organization, r.to_assigned_org_id or r.to_owner_org_id) if (r.to_assigned_org_id or r.to_owner_org_id) else None
        out.append({
            'id': r.id,
            'vehicle_id': r.vehicle_id,
            'vehicle_plate': veh.plate if veh else None,
            'vehicle_brand_model': f"{veh.brand or ''} {veh.model or ''}".strip() if veh else None,
            'from_org_name': from_org.name if from_org else (r.from_assigned_text or '—'),
            'to_org_name': to_org.name if to_org else (r.to_assigned_text or '—'),
            'basis': r.basis,
            'doc_number': r.doc_number,
            'doc_date': r.doc_date.isoformat() if r.doc_date else None,
            'changed_at': r.changed_at.isoformat() if r.changed_at else None,
        })
    return out


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


def _dedup_key(vin: Optional[str], plate: Optional[str], fallback_id: int) -> str:
    """Phase 29.3-R3 (pt-dedup): нормализованный ключ дедубликации.
    Приоритет: VIN (если есть) → plate (нормализованный) → __id_<n>.
    """
    if vin and vin.strip():
        return ("vin:" + vin.upper().replace(" ", "").strip())
    if plate and plate.strip():
        return ("plate:" + plate.upper().replace(" ", "").strip())
    return f"__id_{fallback_id}"


_STATE_PRIORITY = {
    "broken": 4, "destroyed": 4, "utilized": 4, "needs_repair": 3,
    "in_repair": 3, "working": 1, "unknown": 0, "": 0, None: 0,
}
def _state_rank(s):
    return _STATE_PRIORITY.get(s, 2)


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

    # Phase 29.3R-2: показывать ТС либо с open repair, либо со state IN (in_repair, broken, needs_repair)
    # без VehicleRepair записи (state может быть выставлен напрямую без создания repair-записи).
    repair_states = ("in_repair", "broken", "needs_repair")
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
        .outerjoin(open_repair_sq, open_repair_sq.c.vehicle_id == Vehicle.id)
        .outerjoin(photo_sq, photo_sq.c.vehicle_id == Vehicle.id)
        .where(
            or_(
                open_repair_sq.c.vehicle_id.is_not(None),
                func.lower(func.coalesce(Vehicle.state, "")).in_(repair_states),
            )
        )
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
        # value = label (например "Работает") → find internal state key
        reverse_labels = {v: k for k, v in _STATE_LABELS.items()}
        state_key = reverse_labels.get(value, value)
        # Robust: case-insensitive + trim (защита от заглавных букв / пробелов в БД)
        state_norm = state_key.lower().strip() if state_key else ""
        q = (
            base_q
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(Organization.name.label("owner_org_name"))
            .where(func.lower(func.coalesce(Vehicle.state, "")) == state_norm)
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r) for r in rows]

        # Phase 29.2 diagnostic: если результат пуст, логируем distinct values
        # которые видны user'у — это вскроет case/whitespace/NULL mismatch.
        if not items:
            try:
                diag_q = select(Vehicle.state, func.count(Vehicle.id).label("cnt"))
                diag_q = _apply_visibility(diag_q, current_user)
                diag_q = diag_q.group_by(Vehicle.state)
                diag_rows = (await db.execute(diag_q)).all()
                import logging
                logging.warning(
                    f"[vehicles_drill donut_state] EMPTY result; "
                    f"value={value!r} state_key={state_key!r} state_norm={state_norm!r}; "
                    f"distinct states in visible DB: "
                    f"{[(r[0], int(r[1] or 0)) for r in diag_rows]}"
                )
            except Exception as exc:
                import logging
                logging.warning(f"[vehicles_drill donut_state] diag failed: {exc!r}")

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

    elif dimension == "region":
        # value = assigned_text string → vehicles WHERE assigned_text = value
        q = (
            base_q
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(Organization.name.label("owner_org_name"))
            .where(Vehicle.assigned_text == value)
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r) for r in rows]

    elif dimension == "state":
        # value = state key string (e.g. 'working', 'in_repair')
        q = (
            base_q
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(Organization.name.label("owner_org_name"))
            .where(func.lower(func.coalesce(Vehicle.state, "")) == (value or "").lower().strip())
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r) for r in rows]

    elif dimension == "warning":
        # value = 'all' → all vehicles with active maintenance warnings
        today = date.today()
        horizon = today + timedelta(days=30)
        q = (
            base_q
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(Organization.name.label("owner_org_name"))
            .where(
                or_(
                    and_(Vehicle.insurance_until.is_not(None), Vehicle.insurance_until <= horizon),
                    and_(Vehicle.next_to_km.is_not(None), Vehicle.current_odometer_km.is_not(None),
                         (Vehicle.next_to_km - Vehicle.current_odometer_km) < 1000),
                )
            )
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r) for r in rows]

    else:
        return {"items": [], "total": 0, "dimension": dimension, "value": value}

    return {"items": items, "total": len(items), "dimension": dimension, "value": value}


# ─────────────────────────── 10. Expiring docs drill ─────────────────────────

@router.get("/expiring-docs-drill")
async def expiring_docs_drill(
    days: int = Query(30, ge=1, le=365, description="Горизонт в днях"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
) -> dict:
    """Drill для KPI «Документы истекают»: ТС + водители с истекающими документами."""
    today = date.today()
    horizon = today + timedelta(days=days)

    # === ТС с истекающими документами ===
    vehicles_q = select(Vehicle).where(
        or_(
            and_(Vehicle.insurance_until.isnot(None), Vehicle.insurance_until <= horizon),
            and_(Vehicle.tech_inspection_until.isnot(None), Vehicle.tech_inspection_until <= horizon),
        )
    )
    vis_clause = _visibility_filter(current_user)
    if vis_clause is not None:
        vehicles_q = vehicles_q.where(vis_clause)

    v_rows = (await db.execute(vehicles_q)).scalars().unique().all()

    vehicles_out = []
    for v in v_rows:
        expiring = []
        if v.insurance_until and v.insurance_until <= horizon:
            expiring.append({
                "type": "osago",
                "label": "ОСАГО",
                "expires_at": v.insurance_until.isoformat(),
                "days_left": (v.insurance_until - today).days,
            })
        if v.tech_inspection_until and v.tech_inspection_until <= horizon:
            expiring.append({
                "type": "tech_inspection",
                "label": "Технический осмотр",
                "expires_at": v.tech_inspection_until.isoformat(),
                "days_left": (v.tech_inspection_until - today).days,
            })
        if not expiring:
            continue
        vehicles_out.append({
            "id": v.id,
            "plate": v.plate,
            "brand": v.brand,
            "model": v.model,
            "state": v.state,
            "expiring_docs": expiring,
        })

    # === Водители с истекающими документами ===
    drivers_q = select(User).where(
        User.can_drive == True,
        or_(
            and_(User.license_expires_at.isnot(None), User.license_expires_at <= horizon),
            and_(User.medical_cert_expires_at.isnot(None), User.medical_cert_expires_at <= horizon),
            and_(User.tachograph_card_expires_at.isnot(None), User.tachograph_card_expires_at <= horizon),
            and_(User.psych_cert_expires_at.isnot(None), User.psych_cert_expires_at <= horizon),
            and_(User.periodic_medical_expires_at.isnot(None), User.periodic_medical_expires_at <= horizon),
        )
    )
    # Org visibility for drivers: filter by org_ids the current user can see
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        drivers_q = drivers_q.where(User.org_id.in_(org_ids))

    d_rows = (await db.execute(drivers_q)).scalars().unique().all()

    drivers_out = []
    for u in d_rows:
        expiring = []
        for field, type_key, label in [
            ("license_expires_at", "license", "Водительское удостоверение"),
            ("medical_cert_expires_at", "medical", "Медсправка водителя"),
            ("periodic_medical_expires_at", "periodic_medical", "Периодический медосмотр (302-пр.)"),
            ("psych_cert_expires_at", "psych", "Психиатрия (302-пр.)"),
            ("tachograph_card_expires_at", "tachograph", "Карточка тахографа"),
        ]:
            val = getattr(u, field, None)
            if val and val <= horizon:
                expiring.append({
                    "type": type_key,
                    "label": label,
                    "expires_at": val.isoformat(),
                    "days_left": (val - today).days,
                })
        if not expiring:
            continue
        drivers_out.append({
            "id": u.id,
            "full_name": u.full_name or u.username,
            "fleet_role": u.fleet_role,
            "expiring_docs": expiring,
        })

    # Сортировка по min days_left (самые срочные сверху)
    vehicles_out.sort(key=lambda x: min(d["days_left"] for d in x["expiring_docs"]))
    drivers_out.sort(key=lambda x: min(d["days_left"] for d in x["expiring_docs"]))

    return {
        "vehicles": vehicles_out,
        "drivers": drivers_out,
        "horizon_days": days,
        "horizon_date": horizon.isoformat(),
    }


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
            Vehicle.vin,
            Vehicle.brand,
            Vehicle.model,
            Vehicle.state,
            Vehicle.insurance_until,
            Vehicle.assigned_text,
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

    # Phase 29.3-R3: дедубликация по VIN→plate→id (см. _dedup_key)
    seen: dict[str, dict] = {}
    for r in rows:
        norm = _dedup_key(getattr(r, "vin", None), r.plate, r.id)
        item = {
            "vehicle_id": r.id,
            "plate": r.plate or "",
            "brand_model": f"{r.brand or ''} {r.model or ''}".strip() or (r.plate or ""),
            "state": r.state or "unknown",
            "owner_org_name": r.owner_org_name or "",
            "assigned_text": r.assigned_text or "",
            "fuel_cost": float(r.fuel_cost or 0),
            "repair_cost": float(r.repair_cost or 0),
            "mileage_km": int(r.mileage_km or 0),
            "insurance_overdue": (
                r.insurance_until is not None and r.insurance_until < today
            ),
            "insurance_until": r.insurance_until.isoformat() if r.insurance_until else None,
        }
        prev = seen.get(norm)
        # Phase 29.3-R3 (pt-tie): при равном state_rank — выигрывает запись с non-empty assigned_text
        # (это устраняет mismatch между /by-region (по assigned_text) и /all-vehicles-summary).
        if not prev:
            seen[norm] = item
        else:
            cur_rank = _state_rank(item["state"])
            prev_rank = _state_rank(prev["state"])
            cur_has_region = bool(item.get("assigned_text"))
            prev_has_region = bool(prev.get("assigned_text"))
            if cur_rank > prev_rank or (cur_rank == prev_rank and cur_has_region and not prev_has_region):
                seen[norm] = item
    return list(seen.values())


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
    # Phase 29.3-R3: дедубликация по VIN→plate→id
    q = (
        select(Vehicle.id, Vehicle.vin, Vehicle.plate, Vehicle.state, Vehicle.assigned_text)
    )
    q = _apply_visibility(q, current_user)
    raw_rows = (await db.execute(q)).all()

    seen_v: dict[str, dict] = {}
    for r in raw_rows:
        norm = _dedup_key(r.vin, r.plate, r.id)
        cur = {"region": (r.assigned_text or "Не указан").strip(), "state": r.state or "unknown"}
        prev = seen_v.get(norm)
        if not prev or _state_rank(cur["state"]) > _state_rank(prev["state"]):
            seen_v[norm] = cur

    region_map: dict = {}
    for v in seen_v.values():
        rg = v["region"]
        if rg not in region_map:
            region_map[rg] = {"region": rg, "count": 0, "by_state": {}}
        region_map[rg]["count"] += 1
        sk = v["state"]
        region_map[rg]["by_state"][sk] = region_map[rg]["by_state"].get(sk, 0) + 1

    result = sorted(region_map.values(), key=lambda x: x["count"], reverse=True)

    # штаб_label heuristic — map common region strings
    _SHTAB = {
        "Ростов-на-Дону": "филиал РНД, СТО",
        "ЦУ Москва": "филиал ЦУ",
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

    # Phase 29.3-R3: дедубликация по VIN→plate→id
    raw_q = select(Vehicle.id, Vehicle.vin, Vehicle.plate, Vehicle.state)
    raw_q = _apply_visibility(raw_q, current_user)
    raw_rows = (await db.execute(raw_q)).all()

    seen_v: dict[str, tuple[int, str]] = {}  # norm_key -> (id, state)
    for r in raw_rows:
        norm = _dedup_key(r.vin, r.plate, r.id)
        prev = seen_v.get(norm)
        if not prev or _state_rank(r.state) > _state_rank(prev[1]):
            seen_v[norm] = (r.id, r.state or "unknown")

    unique_ids = {v[0] for v in seen_v.values()}
    total_all = len(unique_ids)
    state_map: dict = {}
    for _id, st in seen_v.values():
        state_map[st] = state_map.get(st, 0) + 1

    working = state_map.get("working", 0)
    # in_repair bucket mirrors frontend filteredVehicles: ['in_repair', 'broken', 'needs_repair']
    in_repair = (
        state_map.get("in_repair", 0)
        + state_map.get("broken", 0)
        + state_map.get("needs_repair", 0)
    )
    # not_running bucket: destroyed + utilized (списаны/утилизированы)
    not_running = (
        state_map.get("destroyed", 0)
        + state_map.get("utilized", 0)
    )

    # No report in 30d: working vehicles with NO odometer record in last 30 days
    recent_odo_sq = (
        select(VehicleOdometer.vehicle_id)
        .where(VehicleOdometer.date >= cutoff_30d)
        .distinct()
    ).subquery("recent_odo")

    no_report_q = (
        select(Vehicle.id)
        .outerjoin(recent_odo_sq, recent_odo_sq.c.vehicle_id == Vehicle.id)
        .where(recent_odo_sq.c.vehicle_id.is_(None))
        .where(Vehicle.state == "working")
    )
    no_report_q = _apply_visibility(no_report_q, current_user)
    no_report_ids = {r.id for r in (await db.execute(no_report_q)).all()}
    no_report_30d = len(no_report_ids & unique_ids)

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


# ─────────────────────────── Fine Leaders (Phase 29.3-fines) ─────────────────


@router.get("/fine-leaders")
async def fine_leaders(
    kind: str = Query("drivers", description="Тип рейтинга: drivers | vehicles | filials"),
    limit: int = Query(10, ge=1, le=50),
    period_days: Optional[int] = Query(None, description="Окно за последние N дней; None = все"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Топ по штрафам — пьедестал. kind=drivers|vehicles|filials.

    drivers: группировка по водителю (snapshot + fallback JOIN trips).
    vehicles: группировка по ТС (plate / brand+model).
    filials: группировка по организации-владельцу ТС (owner_org_id).
    """
    period_filter = ""
    if period_days is not None:
        period_filter = f"AND f.issued_at >= NOW() - INTERVAL '{int(period_days)} days'"

    if kind == "vehicles":
        sql = text(f"""
            SELECT
                v.id::text                                             AS entity_key,
                COALESCE(v.plate, '—')                                AS entity_name,
                TRIM(CONCAT(COALESCE(v.brand,''), ' ', COALESCE(v.model,''))) AS entity_sub,
                v.id                                                  AS entity_id,
                COUNT(f.id)::int                                      AS fines_count,
                SUM(f.amount)                                         AS fines_total,
                COUNT(f.id) FILTER (WHERE f.status = 'unpaid')::int   AS unpaid_count,
                COALESCE(SUM(f.amount) FILTER (WHERE f.status = 'unpaid'), 0) AS unpaid_total
            FROM vehicle_fines f
            JOIN vehicles v ON v.id = f.vehicle_id
            WHERE 1=1 {period_filter}
            GROUP BY v.id, v.plate, v.brand, v.model
            ORDER BY fines_total DESC NULLS LAST
            LIMIT :lim
        """)
        rows = (await db.execute(sql, {"lim": limit})).mappings().all()
        return [
            {
                "entity_key": r["entity_key"],
                "entity_name": r["entity_name"],
                "entity_sub": r["entity_sub"],
                "entity_id": r["entity_id"],
                "fines_count": r["fines_count"],
                "fines_total": float(r["fines_total"] or 0),
                "unpaid_count": r["unpaid_count"],
                "unpaid_total": float(r["unpaid_total"] or 0),
            }
            for r in rows
        ]

    if kind == "filials":
        sql = text(f"""
            SELECT
                o.id::text                                             AS entity_key,
                COALESCE(o.name, '— Без филиала —')                   AS entity_name,
                NULL                                                   AS entity_sub,
                o.id                                                   AS entity_id,
                COUNT(f.id)::int                                       AS fines_count,
                SUM(f.amount)                                          AS fines_total,
                COUNT(f.id) FILTER (WHERE f.status = 'unpaid')::int    AS unpaid_count,
                COALESCE(SUM(f.amount) FILTER (WHERE f.status = 'unpaid'), 0) AS unpaid_total
            FROM vehicle_fines f
            JOIN vehicles v ON v.id = f.vehicle_id
            LEFT JOIN organizations o ON o.id = v.owner_org_id
            WHERE 1=1 {period_filter}
            GROUP BY o.id, o.name
            ORDER BY fines_total DESC NULLS LAST
            LIMIT :lim
        """)
        rows = (await db.execute(sql, {"lim": limit})).mappings().all()
        return [
            {
                "entity_key": r["entity_key"],
                "entity_name": r["entity_name"],
                "entity_sub": r["entity_sub"],
                "entity_id": r["entity_id"],
                "fines_count": r["fines_count"],
                "fines_total": float(r["fines_total"] or 0),
                "unpaid_count": r["unpaid_count"],
                "unpaid_total": float(r["unpaid_total"] or 0),
            }
            for r in rows
        ]

    # kind == "drivers" (default)
    sql = text(f"""
        WITH matched AS (
            SELECT
                f.id,
                f.amount,
                f.status,
                COALESCE(f.driver_user_id, t.driver_user_id)         AS user_id,
                COALESCE(f.driver_external_id, t.driver_external_id) AS ext_id
            FROM vehicle_fines f
            LEFT JOIN trips t
                ON t.vehicle_id = f.vehicle_id
               AND t.date = (f.issued_at AT TIME ZONE 'UTC')::date
            WHERE 1=1 {period_filter}
        )
        SELECT
            CASE
                WHEN user_id IS NOT NULL THEN 'user-' || user_id::text
                WHEN ext_id  IS NOT NULL THEN 'ext-'  || ext_id::text
                ELSE 'unmatched'
            END                                                    AS driver_key,
            COALESCE(u.full_name, ext.full_name, '— Не определён —') AS driver_name,
            CASE
                WHEN user_id IS NOT NULL THEN 'user'
                WHEN ext_id  IS NOT NULL THEN 'external'
                ELSE 'unmatched'
            END                                                    AS driver_kind,
            CASE
                WHEN user_id IS NOT NULL THEN user_id
                WHEN ext_id  IS NOT NULL THEN ext_id
                ELSE NULL
            END                                                    AS driver_id,
            COUNT(*)::int                                          AS fines_count,
            SUM(amount)                                            AS fines_total,
            COUNT(*) FILTER (WHERE status = 'unpaid')::int         AS unpaid_count,
            COALESCE(SUM(amount) FILTER (WHERE status = 'unpaid'), 0) AS unpaid_total
        FROM matched
        LEFT JOIN users u   ON u.id   = user_id
        LEFT JOIN external_drivers ext ON ext.id = ext_id
        GROUP BY driver_key, driver_name, driver_kind, driver_id
        ORDER BY fines_total DESC NULLS LAST
        LIMIT :lim
    """)

    rows = (await db.execute(sql, {"lim": limit})).mappings().all()
    return [
        {
            "driver_key": r["driver_key"],
            "driver_name": r["driver_name"],
            "driver_kind": r["driver_kind"],
            "driver_id": r["driver_id"],
            "fines_count": r["fines_count"],
            "fines_total": float(r["fines_total"] or 0),
            "unpaid_count": r["unpaid_count"],
            "unpaid_total": float(r["unpaid_total"] or 0),
        }
        for r in rows
    ]


@router.get("/fines-summary")
async def fines_summary(
    period_days: Optional[int] = Query(None, description="Окно за последние N дней; None = все"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Агрегированные счётчики штрафов по всему автопарку.
    Используется для KPI-карточек в дашборде.
    """
    from app.models.vehicle_fine import VehicleFine

    q = select(
        func.count(VehicleFine.id).label("total_count"),
        func.coalesce(func.sum(VehicleFine.amount), 0).label("total_amount"),
        func.count(VehicleFine.id).filter(VehicleFine.status == "unpaid").label("unpaid_count"),
        func.coalesce(
            func.sum(VehicleFine.amount).filter(VehicleFine.status == "unpaid"), 0
        ).label("unpaid_amount"),
    )
    if period_days is not None:
        from sqlalchemy import func as safunc
        from datetime import timezone as tz
        import datetime as dt_mod
        cutoff = dt_mod.datetime.now(tz.utc) - dt_mod.timedelta(days=period_days)
        q = q.where(VehicleFine.issued_at >= cutoff)

    row = (await db.execute(q)).first()
    return {
        "total_count": row.total_count if row else 0,
        "total_amount": float(row.total_amount) if row else 0.0,
        "unpaid_count": row.unpaid_count if row else 0,
        "unpaid_amount": float(row.unpaid_amount) if row else 0.0,
    }


@router.get("/fines-by-filial")
async def fines_by_filial(
    period_days: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Phase 29.3-R3 (pt11): штрафы по филиалам (Vehicle.owner_org_id → Organization.name).
    Возвращает: [{org_id, org_name, total_count, total_amount, unpaid_count, unpaid_amount, overdue_count}]
    """
    from app.models.vehicle_fine import VehicleFine
    import datetime as dt_mod
    from datetime import timezone as tz

    now_utc = dt_mod.datetime.now(tz.utc)
    overdue_cutoff = now_utc + dt_mod.timedelta(days=7)  # «скоро срок» <7 дней — пока используем как proxy «overdue»

    q = (
        select(
            Organization.id.label("org_id"),
            Organization.name.label("org_name"),
            func.count(VehicleFine.id).label("total_count"),
            func.coalesce(func.sum(VehicleFine.amount), 0).label("total_amount"),
            func.count(VehicleFine.id).filter(VehicleFine.status == "unpaid").label("unpaid_count"),
            func.coalesce(
                func.sum(VehicleFine.amount).filter(VehicleFine.status == "unpaid"), 0
            ).label("unpaid_amount"),
        )
        .select_from(VehicleFine)
        .join(Vehicle, Vehicle.id == VehicleFine.vehicle_id)
        .join(Organization, Organization.id == Vehicle.owner_org_id)
        .group_by(Organization.id, Organization.name)
        .order_by(func.sum(VehicleFine.amount).desc())
    )
    if period_days is not None:
        cutoff = now_utc - dt_mod.timedelta(days=period_days)
        q = q.where(VehicleFine.issued_at >= cutoff)

    rows = (await db.execute(q)).all()
    return [{
        "org_id": r.org_id,
        "org_name": r.org_name,
        "total_count": int(r.total_count or 0),
        "total_amount": float(r.total_amount or 0),
        "unpaid_count": int(r.unpaid_count or 0),
        "unpaid_amount": float(r.unpaid_amount or 0),
    } for r in rows]
