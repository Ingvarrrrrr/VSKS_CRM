"""
Trips (путевые листы) router — ядро. Plan 29-08, Phase 29 «Имущество → Автотранспорт».

Decisions covered: D-14, D-19.

РЕЗКА (Правило №5, сессия 2026-09-08): монолит 1204 строки разрезан на ядро +
соседей с тем же префиксом /api/trips (по образцу users.py → users_access.py,
git ca7b02c). Ядро — CRUD поездок + общие хелперы, которые ИМПОРТИРУЮТ соседи
(не дублируют — Правило №6): _can_see_vehicle, _load_trip_or_404, _trip_to_dict.

Соседи:
  app/routers/trips_reports.py   — GET /stats, GET /last-fuel.
                                    Регистрируется в app/routes.py ДО ядра —
                                    иначе Starlette матчит их на catch-all
                                    GET /{trip_id} ядра и FastAPI падает 422
                                    при попытке привести "stats"/"last-fuel" к int.
  app/routers/trips_status.py    — workflow-переходы статусов (Phase 30-PR3):
                                    tech-inspect, med-inspect, post-trip-mechanic,
                                    post-trip-doctor, driver-sign, close.
  app/routers/trips_waybill.py   — печать путевого листа: legacy docxtpl-render
                                    + .docx/.xlsx выгрузки (D-14, D-19).
  app/routers/trips_telemetry.py — дочерние сущности ПЛ: route-stops,
                                    odometer-readings, fuel-refills.

Ядровые эндпоинты:
  GET    /api/trips                   — list (vehicle_id, date_from, date_to, status filters)
  POST   /api/trips                   — create, require_action('vehicle.trip.create')
  GET    /api/trips/{trip_id}         — detail
  PATCH  /api/trips/{trip_id}         — partial update
  DELETE /api/trips/{trip_id}         — hard delete
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth.jwt import get_org_filter, ADMIN_ROLES
from app.auth.permissions import require_tab, require_action
from app.models.trip import Trip
from app.models.vehicle import Vehicle
from app.models.user import User
from app.models.external_driver import ExternalDriver
from app.services.waybill_numbering import generate_waybill_number

router = APIRouter(prefix="/api/trips", tags=["vehicles"])

# ─────────────────────── Date helpers ───────────────────────────────────────

_DATE_FIELDS = {"date"}


def _coerce_date(value):
    """Parse ISO date string → date object, or pass through if already date."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value if isinstance(value, date) else value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


# ─────────────────────── Visibility helper ──────────────────────────────────

def _can_see_vehicle(vehicle: Vehicle, current_user: User) -> bool:
    """Admin or superadmin can see all. Others — only their org's vehicles."""
    if current_user.role in ADMIN_ROLES:
        return True
    org_filter = get_org_filter(current_user)
    if org_filter is None:
        return True  # superadmin
    return vehicle.owner_org_id == current_user.org_id or vehicle.assigned_org_id == current_user.org_id


# ─────────────────────── GET /api/trips ─────────────────────────────────────

@router.get("")
async def list_trips(
    vehicle_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    q = select(Trip).options(
        selectinload(Trip.vehicle),
        selectinload(Trip.driver_user),
        selectinload(Trip.driver_external),
    )

    if vehicle_id is not None:
        q = q.where(Trip.vehicle_id == vehicle_id)
    if date_from:
        q = q.where(Trip.date >= _coerce_date(date_from))
    if date_to:
        q = q.where(Trip.date <= _coerce_date(date_to))
    if status:
        q = q.where(Trip.status == status)

    q = q.order_by(Trip.date.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    trips = result.scalars().all()

    # Visibility filter
    visible = [t for t in trips if t.vehicle and _can_see_vehicle(t.vehicle, current_user)]

    return [_trip_to_dict(t) for t in visible]


# ─────────────────────── GET /api/trips/{trip_id} ───────────────────────────

@router.get("/{trip_id}")
async def get_trip(
    trip_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _load_trip_or_404(trip_id, db)
    if not _can_see_vehicle(trip.vehicle, current_user):
        raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Нет доступа к этому ТС"})
    return _trip_to_dict(trip)


# ─────────────────────── POST /api/trips ────────────────────────────────────

@router.post("")
async def create_trip(
    body: dict = Body(...),
    current_user: User = Depends(require_action("vehicle.trip.create")),
    db: AsyncSession = Depends(get_db),
):
    vehicle_id = body.get("vehicle_id")
    if not vehicle_id:
        raise HTTPException(422, detail={
            "code": "VEHICLE_REQUIRED",
            "message": "Выберите транспортное средство для путевого листа",
        })

    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "ТС не найдено"})
    if not _can_see_vehicle(vehicle, current_user):
        raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Нет доступа к этому ТС"})

    # XOR check: exactly one of driver_user_id / driver_external_id
    driver_user_id = body.get("driver_user_id")
    driver_external_id = body.get("driver_external_id")
    if not driver_user_id and not driver_external_id:
        raise HTTPException(422, detail={
            "code": "DRIVER_REQUIRED",
            "message": "Укажите штатного или внешнего водителя",
        })
    if driver_user_id and driver_external_id:
        raise HTTPException(422, detail={
            "code": "DRIVER_REQUIRED",
            "message": "Укажите только одного водителя: штатного ИЛИ внешнего",
        })

    # Validate can_drive for User driver
    if driver_user_id:
        driver = await db.get(User, int(driver_user_id))
        if not driver:
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Пользователь-водитель не найден"})
        if not getattr(driver, "can_drive", False):
            raise HTTPException(422, detail={
                "code": "DRIVER_NOT_ELIGIBLE",
                "message": "Пользователь не имеет прав водителя (can_drive=False)",
            })

    # Validate ExternalDriver FK
    if driver_external_id:
        ext_driver = await db.get(ExternalDriver, int(driver_external_id))
        if not ext_driver:
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Внешний водитель не найден"})

    # Date parsing
    trip_date = body.get("date")
    if not trip_date:
        raise HTTPException(422, detail={"code": "DATE_REQUIRED", "message": "Дата путёвки обязательна"})
    trip_date = _coerce_date(trip_date)

    # odometer_start fallback from vehicle
    odo_start = body.get("odometer_start")
    if odo_start is None:
        odo_start = vehicle.current_odometer_km

    # Phase 30: auto-assign waybill number if not provided
    waybill_number = body.get("number")
    if not waybill_number:
        waybill_number = await generate_waybill_number(db)

    trip = Trip(
        vehicle_id=vehicle_id,
        date=trip_date,
        driver_user_id=int(driver_user_id) if driver_user_id else None,
        driver_external_id=int(driver_external_id) if driver_external_id else None,
        route_from=body.get("route_from"),
        route_to=body.get("route_to"),
        purpose=body.get("purpose"),
        odometer_start=int(odo_start) if odo_start is not None else None,
        odometer_finish=int(body["odometer_finish"]) if body.get("odometer_finish") is not None else None,
        fuel_remaining_start=body.get("fuel_remaining_start"),
        fuel_remaining_finish=body.get("fuel_remaining_finish"),
        fuel_issued_l=body.get("fuel_issued_l"),
        cargo_name=body.get("cargo_name"),
        cargo_weight_t=body.get("cargo_weight_t"),
        status="draft",
        created_by_id=current_user.id,
        number=waybill_number,
    )
    db.add(trip)
    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── PATCH /api/trips/{trip_id} ─────────────────────────

@router.patch("/{trip_id}")
async def patch_trip(
    trip_id: int,
    body: dict = Body(...),
    current_user: User = Depends(require_action("vehicle.trip.create")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _load_trip_or_404(trip_id, db)
    if not _can_see_vehicle(trip.vehicle, current_user):
        raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Нет доступа к этому ТС"})

    # XOR validation if driver fields present
    new_duid = body.get("driver_user_id", ...)
    new_deid = body.get("driver_external_id", ...)
    if new_duid is not ... or new_deid is not ...:
        resolved_duid = body.get("driver_user_id") if new_duid is not ... else trip.driver_user_id
        resolved_deid = body.get("driver_external_id") if new_deid is not ... else trip.driver_external_id
        if not resolved_duid and not resolved_deid:
            raise HTTPException(422, detail={
                "code": "DRIVER_REQUIRED",
                "message": "Укажите штатного или внешнего водителя",
            })
        if resolved_duid and resolved_deid:
            raise HTTPException(422, detail={
                "code": "DRIVER_REQUIRED",
                "message": "Укажите только одного водителя: штатного ИЛИ внешнего",
            })

    _PATCHABLE = {
        "route_from", "route_to", "purpose",
        "odometer_start", "odometer_finish",
        "fuel_remaining_start", "fuel_remaining_finish", "fuel_issued_l",
        "cargo_name", "cargo_weight_t",
        "driver_user_id", "driver_external_id",
        "status", "date",
    }
    for key, val in body.items():
        if key not in _PATCHABLE:
            continue
        if key in _DATE_FIELDS and val is not None:
            val = _coerce_date(val)
        setattr(trip, key, val)

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── DELETE /api/trips/{trip_id} ────────────────────────

@router.delete("/{trip_id}")
async def delete_trip(
    trip_id: int,
    current_user: User = Depends(require_action("vehicle.trip.create")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _load_trip_or_404(trip_id, db)
    if not _can_see_vehicle(trip.vehicle, current_user):
        raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Нет доступа к этому ТС"})
    await db.delete(trip)
    await db.commit()
    return {"ok": True}


# ─────────────────────── Internal helpers (используются соседями) ───────────

async def _load_trip_or_404(trip_id: int, db: AsyncSession) -> Trip:
    result = await db.execute(
        select(Trip)
        .options(
            selectinload(Trip.vehicle),
            selectinload(Trip.driver_user),
            selectinload(Trip.driver_external),
        )
        .where(Trip.id == trip_id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Путевой лист не найден"})
    return trip


def _trip_to_dict(trip: Trip) -> dict:
    return {
        "id": trip.id,
        "vehicle_id": trip.vehicle_id,
        "date": trip.date.isoformat() if trip.date else None,
        "driver_user_id": trip.driver_user_id,
        "driver_external_id": trip.driver_external_id,
        "driver_full_name": (
            (trip.driver_user.full_name if trip.driver_user else None)
            or (trip.driver_external.full_name if trip.driver_external else None)
        ),
        "route_from": trip.route_from,
        "route_to": trip.route_to,
        "purpose": trip.purpose,
        "odometer_start": trip.odometer_start,
        "odometer_finish": trip.odometer_finish,
        "fuel_remaining_start": float(trip.fuel_remaining_start) if trip.fuel_remaining_start is not None else None,
        "fuel_remaining_finish": float(trip.fuel_remaining_finish) if trip.fuel_remaining_finish is not None else None,
        "fuel_issued_l": float(trip.fuel_issued_l) if trip.fuel_issued_l is not None else None,
        "cargo_name": trip.cargo_name,
        "cargo_weight_t": float(trip.cargo_weight_t) if trip.cargo_weight_t is not None else None,
        "docx_path": trip.docx_path,
        "status": trip.status,
        "created_at": trip.created_at.isoformat() if trip.created_at else None,
        "created_by_id": trip.created_by_id,
        # Phase 30 waybill fields
        "number": trip.number,
        "date_start": trip.date_start.isoformat() if trip.date_start else None,
        "date_end": trip.date_end.isoformat() if trip.date_end else None,
        "planned_mileage_km": trip.planned_mileage_km,
        "actual_mileage_km": trip.actual_mileage_km,
        "dispatcher_id": trip.dispatcher_id,
        "cargo_description": trip.cargo_description,
        "passengers_count": trip.passengers_count,
        "pre_trip_mechanic_id": trip.pre_trip_mechanic_id,
        "pre_trip_mechanic_inspected_at": trip.pre_trip_mechanic_inspected_at.isoformat() if trip.pre_trip_mechanic_inspected_at else None,
        "pre_trip_mechanic_result": trip.pre_trip_mechanic_result,
        "pre_trip_doctor_id": trip.pre_trip_doctor_id,
        "pre_trip_doctor_inspected_at": trip.pre_trip_doctor_inspected_at.isoformat() if trip.pre_trip_doctor_inspected_at else None,
        "pre_trip_doctor_result": trip.pre_trip_doctor_result,
        "post_trip_mechanic_id": trip.post_trip_mechanic_id,
        "post_trip_mechanic_inspected_at": trip.post_trip_mechanic_inspected_at.isoformat() if trip.post_trip_mechanic_inspected_at else None,
        "post_trip_mechanic_result": trip.post_trip_mechanic_result,
        "post_trip_doctor_id": trip.post_trip_doctor_id,
        "post_trip_doctor_inspected_at": trip.post_trip_doctor_inspected_at.isoformat() if trip.post_trip_doctor_inspected_at else None,
        "post_trip_doctor_result": trip.post_trip_doctor_result,
        "driver_signed_at": trip.driver_signed_at.isoformat() if trip.driver_signed_at else None,
    }
