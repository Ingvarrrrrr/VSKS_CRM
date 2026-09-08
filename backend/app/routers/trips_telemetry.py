"""
Trips — дочерние сущности путевого листа (Phase 30-PR3): остановки маршрута,
показания одометра, заправки.

Сосед app/routers/trips.py (Правило №5, резка монолита, сессия 2026-09-08).
ПЕРЕНЕСЕНО без изменений. Тот же префикс /api/trips.

/route-stops/{stop_id}, /odometer-readings/{r_id}, /fuel-refills/{r_id} —
литерал в первом сегменте пути, не конфликтуют с catch-all ядра GET
/{trip_id} (у ядра параметр стоит в первом сегменте, здесь — во втором),
порядок регистрации в app/routes.py относительно ядра не важен.

Использует _load_trip_or_404 из ядра (app.routers.trips) — не дублирует его
(Правило №6). Пробег/одометр — писатели существующие (OdometerReading), новых
не заводится.

Endpoints:
  GET/POST /api/trips/{trip_id}/route-stops
  DELETE   /api/trips/route-stops/{stop_id}
  GET/POST /api/trips/{trip_id}/odometer-readings
  DELETE   /api/trips/odometer-readings/{r_id}
  GET/POST /api/trips/{trip_id}/fuel-refills
  DELETE   /api/trips/fuel-refills/{r_id}
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_tab
from app.models.user import User
from app.models.waybill_children import RouteStop, OdometerReading, FuelRefill
from app.schemas.waybill_workflow import RouteStopIn, OdometerReadingIn, FuelRefillIn
from app.routers.trips import _load_trip_or_404

router = APIRouter(prefix="/api/trips", tags=["vehicles"])


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 30-PR3: Child entity CRUD — route-stops
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/{trip_id}/route-stops")
async def list_route_stops(
    trip_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Список остановок маршрута путевого листа."""
    trip = await _load_trip_or_404(trip_id, db)
    result = await db.execute(
        select(RouteStop).where(RouteStop.waybill_id == trip_id).order_by(RouteStop.ord)
    )
    stops = result.scalars().all()
    return [_route_stop_to_dict(s) for s in stops]


@router.post("/{trip_id}/route-stops")
async def create_route_stop(
    trip_id: int,
    body: RouteStopIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Добавить остановку маршрута."""
    await _load_trip_or_404(trip_id, db)
    stop = RouteStop(
        waybill_id=trip_id,
        ord=body.ord,
        kind=body.kind,
        name=body.name,
        description=body.description,
        planned_time=body.planned_time,
        lat=body.lat,
        lon=body.lon,
    )
    db.add(stop)
    await db.commit()
    await db.refresh(stop)
    return _route_stop_to_dict(stop)


@router.delete("/route-stops/{stop_id}")
async def delete_route_stop(
    stop_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Удалить остановку маршрута."""
    stop = await db.get(RouteStop, stop_id)
    if not stop:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Остановка не найдена"})
    await db.delete(stop)
    await db.commit()
    return {"ok": True}


def _route_stop_to_dict(s: RouteStop) -> dict:
    return {
        "id": s.id,
        "waybill_id": s.waybill_id,
        "ord": s.ord,
        "kind": s.kind,
        "name": s.name,
        "description": s.description,
        "planned_time": s.planned_time.isoformat() if s.planned_time else None,
        "actual_time": s.actual_time.isoformat() if s.actual_time else None,
        "lat": float(s.lat) if s.lat is not None else None,
        "lon": float(s.lon) if s.lon is not None else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 30-PR3: Child entity CRUD — odometer-readings
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/{trip_id}/odometer-readings")
async def list_odometer_readings(
    trip_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Список показаний одометра для путевого листа."""
    await _load_trip_or_404(trip_id, db)
    result = await db.execute(
        select(OdometerReading).where(OdometerReading.waybill_id == trip_id).order_by(OdometerReading.recorded_at)
    )
    readings = result.scalars().all()
    return [_odometer_reading_to_dict(r) for r in readings]


@router.post("/{trip_id}/odometer-readings")
async def create_odometer_reading(
    trip_id: int,
    body: OdometerReadingIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Добавить показание одометра."""
    await _load_trip_or_404(trip_id, db)
    reading = OdometerReading(
        waybill_id=trip_id,
        recorded_at=body.recorded_at,
        location=body.location,
        mileage_km=body.mileage_km,
        fuel_remaining_l=body.fuel_remaining_l,
        note=body.note,
    )
    db.add(reading)
    await db.commit()
    await db.refresh(reading)
    return _odometer_reading_to_dict(reading)


@router.delete("/odometer-readings/{r_id}")
async def delete_odometer_reading(
    r_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Удалить показание одометра."""
    reading = await db.get(OdometerReading, r_id)
    if not reading:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Показание одометра не найдено"})
    await db.delete(reading)
    await db.commit()
    return {"ok": True}


def _odometer_reading_to_dict(r: OdometerReading) -> dict:
    return {
        "id": r.id,
        "waybill_id": r.waybill_id,
        "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
        "location": r.location,
        "mileage_km": r.mileage_km,
        "fuel_remaining_l": float(r.fuel_remaining_l) if r.fuel_remaining_l is not None else None,
        "note": r.note,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 30-PR3: Child entity CRUD — fuel-refills
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/{trip_id}/fuel-refills")
async def list_fuel_refills(
    trip_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Список заправок для путевого листа."""
    await _load_trip_or_404(trip_id, db)
    result = await db.execute(
        select(FuelRefill).where(FuelRefill.waybill_id == trip_id).order_by(FuelRefill.refilled_at)
    )
    refills = result.scalars().all()
    return [_fuel_refill_to_dict(r) for r in refills]


@router.post("/{trip_id}/fuel-refills")
async def create_fuel_refill(
    trip_id: int,
    body: FuelRefillIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Добавить заправку."""
    await _load_trip_or_404(trip_id, db)
    import base64
    photo_bytes = None
    if body.receipt_photo_data:
        try:
            # Strip data-url prefix if present
            raw = body.receipt_photo_data
            if "," in raw:
                raw = raw.split(",", 1)[1]
            photo_bytes = base64.b64decode(raw)
        except Exception:
            raise HTTPException(422, detail={"code": "INVALID_PHOTO", "message": "Неверный формат фото чека (ожидается base64)"})

    refill = FuelRefill(
        waybill_id=trip_id,
        refilled_at=body.refilled_at,
        station_name=body.station_name,
        liters=body.liters,
        amount_rub=body.amount_rub,
        receipt_photo_data=photo_bytes,
    )
    db.add(refill)
    await db.commit()
    await db.refresh(refill)
    return _fuel_refill_to_dict(refill)


@router.delete("/fuel-refills/{r_id}")
async def delete_fuel_refill(
    r_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Удалить заправку."""
    refill = await db.get(FuelRefill, r_id)
    if not refill:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Заправка не найдена"})
    await db.delete(refill)
    await db.commit()
    return {"ok": True}


def _fuel_refill_to_dict(r: FuelRefill) -> dict:
    return {
        "id": r.id,
        "waybill_id": r.waybill_id,
        "refilled_at": r.refilled_at.isoformat() if r.refilled_at else None,
        "station_name": r.station_name,
        "liters": float(r.liters) if r.liters is not None else None,
        "amount_rub": float(r.amount_rub) if r.amount_rub is not None else None,
        "has_receipt_photo": r.receipt_photo_data is not None,
    }
