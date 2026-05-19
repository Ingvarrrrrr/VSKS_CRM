"""
Fuel logs router — Plan 29-07, Phase 29.

Decisions covered: D-03, D-20.

One row = one fueling event.
delta_km and fuel_used_l computed on read.
Seasonal norm: summer = May-Sep, winter = Oct-Apr (D-20).
"""
from datetime import date as date_type, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab, require_action
from app.models.vehicle import Vehicle
from app.models.fuel_log import FuelLog
from app.models.vehicle_odometer import VehicleOdometer
from app.models.user import User

router = APIRouter(prefix="/api/fuel-logs", tags=["vehicles"])

# ── Date fields ───────────────────────────────────────────────────────────────
_DATE_FIELDS = {"date"}


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class FuelLogCreate(BaseModel):
    vehicle_id: int
    date: date_type
    liters: Optional[float] = None
    price_per_liter: Optional[float] = None
    total_amount: Optional[float] = None
    fuel_type: Optional[str] = None
    receipt_attachment_id: Optional[int] = None
    note: Optional[str] = None
    source: Optional[str] = "manual"
    # If provided, also creates a VehicleOdometer entry for that date
    odometer_km: Optional[int] = None


class FuelLogPatch(BaseModel):
    date: Optional[date_type] = None
    liters: Optional[float] = None
    price_per_liter: Optional[float] = None
    total_amount: Optional[float] = None
    fuel_type: Optional[str] = None
    receipt_attachment_id: Optional[int] = None
    note: Optional[str] = None
    source: Optional[str] = None


class FuelLogOut(BaseModel):
    id: int
    vehicle_id: int
    date: date_type
    liters: Optional[float]
    price_per_liter: Optional[float]
    total_amount: Optional[float]
    price_total: Optional[float]   # alias for clarity
    fuel_type: Optional[str]
    receipt_attachment_id: Optional[int]
    note: Optional[str]
    source: str
    created_by_id: Optional[int]
    # Computed
    delta_km: int
    fuel_used_l: float

    class Config:
        from_attributes = True


class LatestPriceOut(BaseModel):
    price_per_liter: Optional[float]
    source: str  # 'latest' | 'org_avg' | 'none'


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_vehicle_or_404(vehicle_id: int, db: AsyncSession) -> Vehicle:
    v = (await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(
            status_code=404,
            detail={"code": "VEHICLE_NOT_FOUND", "message": "Транспортное средство не найдено"},
        )
    return v


async def _get_prev_odometer_km(db: AsyncSession, vehicle_id: int, before_date: date_type) -> Optional[int]:
    """Max odometer_km for vehicle_id WHERE date <= before_date (include same date, other entries)."""
    result = await db.execute(
        select(func.max(VehicleOdometer.odometer_km)).where(
            VehicleOdometer.vehicle_id == vehicle_id,
            VehicleOdometer.date < before_date,
        )
    )
    return result.scalar_one_or_none()


async def _get_odometer_for_date(db: AsyncSession, vehicle_id: int, on_date: date_type) -> Optional[int]:
    """Odometer reading on exact date (for delta computation for fuel log)."""
    result = await db.execute(
        select(VehicleOdometer.odometer_km).where(
            VehicleOdometer.vehicle_id == vehicle_id,
            VehicleOdometer.date == on_date,
        )
    )
    return result.scalar_one_or_none()


def _calc_fuel_used_l(delta_km: int, vehicle: Vehicle, log_date: date_type) -> float:
    """Seasonal fuel consumption norm (D-20)."""
    month = log_date.month
    is_summer = 5 <= month <= 9
    norm = vehicle.fuel_norm_summer if is_summer else vehicle.fuel_norm_winter
    if norm is None or norm <= 0 or delta_km <= 0:
        return 0.0
    return round(delta_km * norm / 100, 2)


async def _to_out(log: FuelLog, db: AsyncSession, vehicle: Optional[Vehicle] = None) -> FuelLogOut:
    if vehicle is None:
        vehicle = await _get_vehicle_or_404(log.vehicle_id, db)

    # delta_km: odometer on this date minus odometer before this date
    current_km = await _get_odometer_for_date(db, log.vehicle_id, log.date)
    prev_km = await _get_prev_odometer_km(db, log.vehicle_id, log.date)

    if current_km is not None and prev_km is not None:
        delta_km = max(current_km - prev_km, 0)
    else:
        delta_km = 0

    fuel_used_l = _calc_fuel_used_l(delta_km, vehicle, log.date)

    liters = float(log.liters) if log.liters is not None else None
    price_per_liter = float(log.price_per_liter) if log.price_per_liter is not None else None
    total_amount = float(log.total_amount) if log.total_amount is not None else None
    price_total = total_amount or (
        round(liters * price_per_liter, 2)
        if liters is not None and price_per_liter is not None
        else None
    )

    return FuelLogOut(
        id=log.id,
        vehicle_id=log.vehicle_id,
        date=log.date,
        liters=liters,
        price_per_liter=price_per_liter,
        total_amount=total_amount,
        price_total=price_total,
        fuel_type=log.fuel_type,
        receipt_attachment_id=log.receipt_attachment_id,
        note=log.note,
        source=log.source,
        created_by_id=log.created_by_id,
        delta_km=delta_km,
        fuel_used_l=fuel_used_l,
    )


async def _update_vehicle_snapshot(db: AsyncSession, vehicle_id: int) -> None:
    """Sync vehicle.current_odometer_km = MAX(odometer_km)."""
    max_km = (await db.execute(
        select(func.max(VehicleOdometer.odometer_km)).where(
            VehicleOdometer.vehicle_id == vehicle_id
        )
    )).scalar_one_or_none()
    vehicle = (await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))).scalar_one_or_none()
    if vehicle:
        vehicle.current_odometer_km = max_km


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/latest-price/{vehicle_id}", response_model=LatestPriceOut)
async def get_latest_price(
    vehicle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    await _get_vehicle_or_404(vehicle_id, db)

    # Latest entry for this vehicle
    latest = (await db.execute(
        select(FuelLog.price_per_liter)
        .where(FuelLog.vehicle_id == vehicle_id, FuelLog.price_per_liter.isnot(None))
        .order_by(FuelLog.date.desc())
        .limit(1)
    )).scalar_one_or_none()

    if latest is not None:
        return LatestPriceOut(price_per_liter=float(latest), source="latest")

    # Org average over last 30 days
    cutoff = date_type.today() - timedelta(days=30)
    vehicle = await _get_vehicle_or_404(vehicle_id, db)
    org_avg = (await db.execute(
        select(func.avg(FuelLog.price_per_liter))
        .join(Vehicle, FuelLog.vehicle_id == Vehicle.id)
        .where(
            Vehicle.owner_org_id == vehicle.owner_org_id,
            FuelLog.date >= cutoff,
            FuelLog.price_per_liter.isnot(None),
        )
    )).scalar_one_or_none()

    if org_avg is not None:
        return LatestPriceOut(price_per_liter=round(float(org_avg), 2), source="org_avg")

    return LatestPriceOut(price_per_liter=None, source="none")


@router.get("/", response_model=List[FuelLogOut])
async def list_fuel_logs(
    vehicle_id: int = Query(...),
    date_from: Optional[date_type] = Query(None),
    date_to: Optional[date_type] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    vehicle = await _get_vehicle_or_404(vehicle_id, db)

    q = (
        select(FuelLog)
        .where(FuelLog.vehicle_id == vehicle_id)
        .order_by(FuelLog.date.desc())
        .limit(limit)
    )
    if date_from:
        q = q.where(FuelLog.date >= date_from)
    if date_to:
        q = q.where(FuelLog.date <= date_to)

    logs = (await db.execute(q)).scalars().all()
    result = []
    for log in logs:
        result.append(await _to_out(log, db, vehicle))
    return result


@router.post("/", response_model=FuelLogOut, status_code=201)
async def create_fuel_log(
    body: FuelLogCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_action("vehicle.odometer.write")),
):
    vehicle = await _get_vehicle_or_404(body.vehicle_id, db)

    # Compute total_amount if not provided
    total_amount = body.total_amount
    if total_amount is None and body.liters is not None and body.price_per_liter is not None:
        total_amount = round(body.liters * body.price_per_liter, 2)

    log = FuelLog(
        vehicle_id=body.vehicle_id,
        date=body.date,
        liters=body.liters,
        price_per_liter=body.price_per_liter,
        total_amount=total_amount,
        fuel_type=body.fuel_type,
        receipt_attachment_id=body.receipt_attachment_id,
        note=body.note,
        source=body.source or "manual",
        created_by_id=current_user.id,
    )
    db.add(log)

    # If odometer_km provided, also create a VehicleOdometer entry
    if body.odometer_km is not None:
        # Check for existing odometer entry on this date
        existing_odo = (await db.execute(
            select(VehicleOdometer).where(
                VehicleOdometer.vehicle_id == body.vehicle_id,
                VehicleOdometer.date == body.date,
            )
        )).scalar_one_or_none()

        if existing_odo is None:
            odo_entry = VehicleOdometer(
                vehicle_id=body.vehicle_id,
                date=body.date,
                odometer_km=body.odometer_km,
                source="fuel_log",
                entered_by_id=current_user.id,
            )
            db.add(odo_entry)

            # Update snapshot
            if vehicle.current_odometer_km is None or body.odometer_km > vehicle.current_odometer_km:
                vehicle.current_odometer_km = body.odometer_km

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "DUPLICATE_FUEL_LOG", "message": "Ошибка сохранения записи о заправке"},
        )

    await db.commit()
    await db.refresh(log)
    return await _to_out(log, db, vehicle)


@router.patch("/{log_id}", response_model=FuelLogOut)
async def patch_fuel_log(
    log_id: int,
    body: FuelLogPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_action("vehicle.odometer.write")),
):
    log = (await db.execute(select(FuelLog).where(FuelLog.id == log_id))).scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Запись не найдена"})

    vehicle = await _get_vehicle_or_404(log.vehicle_id, db)

    patch_data = body.model_dump(exclude_unset=True)
    for field, value in patch_data.items():
        setattr(log, field, value)

    # Recompute total_amount if liters/price changed and total_amount not explicitly set
    if "total_amount" not in patch_data:
        liters = float(log.liters) if log.liters is not None else None
        ppl = float(log.price_per_liter) if log.price_per_liter is not None else None
        if liters is not None and ppl is not None:
            log.total_amount = round(liters * ppl, 2)

    await db.commit()
    await db.refresh(log)
    return await _to_out(log, db, vehicle)


@router.delete("/{log_id}", status_code=204)
async def delete_fuel_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_action("vehicle.odometer.write")),
):
    log = (await db.execute(select(FuelLog).where(FuelLog.id == log_id))).scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Запись не найдена"})

    await db.delete(log)
    await db.commit()
