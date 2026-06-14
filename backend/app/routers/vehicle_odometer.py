"""
Vehicle odometer time-series router — Plan 29-07, Phase 29.

Decisions covered: D-13.

UNIQUE(vehicle_id, date) on DB level.
delta_km computed on read (N+1 — small data, acceptable initially).
vehicle.current_odometer_km snapshot kept in sync.
"""
from datetime import date as date_type
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.permissions import require_tab, require_action
from app.models.vehicle import Vehicle
from app.models.vehicle_odometer import VehicleOdometer
from app.models.user import User

router = APIRouter(prefix="/api/vehicle-odometer", tags=["vehicles"])

# ── Date fields — must be coerced via _coerce (Lesson 2026-05-13) ─────────────
_DATE_FIELDS = {"date"}


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class OdometerCreate(BaseModel):
    vehicle_id: int
    date: date_type
    odometer_km: int
    note: Optional[str] = None
    source: Optional[str] = "manual"


class OdometerPatch(BaseModel):
    date: Optional[date_type] = None
    odometer_km: Optional[int] = None
    note: Optional[str] = None
    source: Optional[str] = None


class OdometerOut(BaseModel):
    id: int
    vehicle_id: int
    date: date_type
    odometer_km: int
    delta_km: int
    fuel_used_l: float
    note: Optional[str]
    source: str
    entered_by_id: Optional[int]

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _assert_vehicle_visible(vehicle: Vehicle, user) -> None:
    org_ids = get_org_filter(user)
    if org_ids is not None and vehicle.owner_org_id not in org_ids and vehicle.assigned_org_id not in org_ids:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Запись не найдена"})


async def _get_vehicle_or_404(vehicle_id: int, db: AsyncSession) -> Vehicle:
    v = (await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail={"code": "VEHICLE_NOT_FOUND", "message": "Транспортное средство не найдено"})
    return v


async def _get_prev_odometer_km(db: AsyncSession, vehicle_id: int, before_date: date_type) -> Optional[int]:
    """Return max odometer_km for vehicle_id WHERE date < before_date."""
    result = await db.execute(
        select(func.max(VehicleOdometer.odometer_km)).where(
            VehicleOdometer.vehicle_id == vehicle_id,
            VehicleOdometer.date < before_date,
        )
    )
    return result.scalar_one_or_none()


def _calc_fuel_used_l(delta_km: int, vehicle: Vehicle, odometer_date: date_type) -> float:
    """Fuel consumption based on summer/winter norm (D-20)."""
    month = odometer_date.month
    is_summer = 5 <= month <= 9
    norm = vehicle.fuel_norm_summer if is_summer else vehicle.fuel_norm_winter
    if norm is None or norm <= 0 or delta_km <= 0:
        return 0.0
    return round(delta_km * norm / 100, 2)


async def _to_out(entry: VehicleOdometer, db: AsyncSession, vehicle: Optional[Vehicle] = None) -> OdometerOut:
    prev_km = await _get_prev_odometer_km(db, entry.vehicle_id, entry.date)
    delta_km = (entry.odometer_km - prev_km) if prev_km is not None else 0
    delta_km = max(delta_km, 0)  # guard against data anomalies

    if vehicle is None:
        vehicle = await _get_vehicle_or_404(entry.vehicle_id, db)

    fuel_used_l = _calc_fuel_used_l(delta_km, vehicle, entry.date)

    return OdometerOut(
        id=entry.id,
        vehicle_id=entry.vehicle_id,
        date=entry.date,
        odometer_km=entry.odometer_km,
        delta_km=delta_km,
        fuel_used_l=fuel_used_l,
        note=entry.note,
        source=entry.source,
        entered_by_id=entry.entered_by_id,
    )


async def _update_vehicle_snapshot(db: AsyncSession, vehicle_id: int) -> None:
    """Atomically set vehicle.current_odometer_km = MAX(odometer_km) for this vehicle."""
    max_km = (await db.execute(
        select(func.max(VehicleOdometer.odometer_km)).where(
            VehicleOdometer.vehicle_id == vehicle_id
        )
    )).scalar_one_or_none()

    vehicle = (await db.execute(
        select(Vehicle).where(Vehicle.id == vehicle_id)
    )).scalar_one_or_none()
    if vehicle:
        vehicle.current_odometer_km = max_km  # None if no entries left


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[OdometerOut])
async def list_odometer(
    vehicle_id: int = Query(...),
    date_from: Optional[date_type] = Query(None),
    date_to: Optional[date_type] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    vehicle = await _get_vehicle_or_404(vehicle_id, db)

    q = (
        select(VehicleOdometer)
        .where(VehicleOdometer.vehicle_id == vehicle_id)
        .order_by(VehicleOdometer.date.desc())
        .limit(limit)
    )
    if date_from:
        q = q.where(VehicleOdometer.date >= date_from)
    if date_to:
        q = q.where(VehicleOdometer.date <= date_to)

    entries = (await db.execute(q)).scalars().all()
    result = []
    for e in entries:
        result.append(await _to_out(e, db, vehicle))
    return result


@router.post("/", response_model=OdometerOut, status_code=201)
async def create_odometer(
    body: OdometerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_action("vehicle.odometer.write")),
):
    vehicle = await _get_vehicle_or_404(body.vehicle_id, db)

    # Monotonic check: new value must be >= previous entry
    prev_km = await _get_prev_odometer_km(db, body.vehicle_id, body.date)
    if prev_km is not None and body.odometer_km < prev_km:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NON_MONOTONIC_ODOMETER",
                "last_km": prev_km,
                "attempted_km": body.odometer_km,
                "message": "Одометр не может уменьшаться",
            },
        )

    entry = VehicleOdometer(
        vehicle_id=body.vehicle_id,
        date=body.date,
        odometer_km=body.odometer_km,
        note=body.note,
        source=body.source or "manual",
        entered_by_id=current_user.id,
    )
    db.add(entry)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE_ODOMETER_DATE",
                "message": "Запись на эту дату уже существует",
            },
        )

    # Update snapshot: set if new value > current snapshot
    if vehicle.current_odometer_km is None or body.odometer_km > vehicle.current_odometer_km:
        vehicle.current_odometer_km = body.odometer_km

    await db.commit()
    await db.refresh(entry)
    return await _to_out(entry, db, vehicle)


@router.patch("/{entry_id}", response_model=OdometerOut)
async def patch_odometer(
    entry_id: int,
    body: OdometerPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_action("vehicle.odometer.write")),
):
    entry = (await db.execute(
        select(VehicleOdometer).where(VehicleOdometer.id == entry_id)
    )).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Запись не найдена"})

    vehicle = await _get_vehicle_or_404(entry.vehicle_id, db)
    _assert_vehicle_visible(vehicle, current_user)

    patch_data = body.model_dump(exclude_unset=True)
    new_odometer_km = patch_data.get("odometer_km", entry.odometer_km)
    new_date = patch_data.get("date", entry.date)

    # Monotonic check against entries before the new date (excluding self)
    prev_km_result = await db.execute(
        select(func.max(VehicleOdometer.odometer_km)).where(
            VehicleOdometer.vehicle_id == entry.vehicle_id,
            VehicleOdometer.date < new_date,
            VehicleOdometer.id != entry_id,
        )
    )
    prev_km = prev_km_result.scalar_one_or_none()
    if prev_km is not None and new_odometer_km < prev_km:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NON_MONOTONIC_ODOMETER",
                "last_km": prev_km,
                "attempted_km": new_odometer_km,
                "message": "Одометр не может уменьшаться",
            },
        )

    for field, value in patch_data.items():
        setattr(entry, field, value)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE_ODOMETER_DATE",
                "message": "Запись на эту дату уже существует",
            },
        )

    await _update_vehicle_snapshot(db, entry.vehicle_id)
    await db.commit()
    await db.refresh(entry)
    return await _to_out(entry, db, vehicle)


@router.delete("/{entry_id}", status_code=204)
async def delete_odometer(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_action("vehicle.odometer.write")),
):
    entry = (await db.execute(
        select(VehicleOdometer).where(VehicleOdometer.id == entry_id)
    )).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Запись не найдена"})

    vehicle = await _get_vehicle_or_404(entry.vehicle_id, db)
    _assert_vehicle_visible(vehicle, current_user)

    vehicle_id = entry.vehicle_id
    await db.delete(entry)
    await db.flush()

    # Recalculate snapshot from remaining entries
    await _update_vehicle_snapshot(db, vehicle_id)
    await db.commit()
