"""
Trips (путевые листы) router — Plan 29-08, Phase 29 «Имущество → Автотранспорт».

Decisions covered: D-14, D-19.

Endpoints:
  GET    /api/trips                   — list (vehicle_id, date_from, date_to, status filters)
  POST   /api/trips                   — create, require_action('vehicle.trip.create')
  GET    /api/trips/{trip_id}         — detail
  PATCH  /api/trips/{trip_id}         — partial update
  DELETE /api/trips/{trip_id}         — hard delete
  POST   /api/trips/{trip_id}/render  — generate .docx via docxtpl (D-14, D-19)

Template selector (D-14):
  car_light / minivan / quadbike / other  → trip_light.docx  (форма 3)
  truck_*                                 → trip_truck.docx   (форма 4-С)
  bus / special / snowmobile / boat /
    boat_motor / trailer                  → trip_special.docx

Registration in __init__.py deferred to separate commit per plan constraint.
"""
import os
import traceback
import logging
from datetime import date, datetime
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter, ADMIN_ROLES
from app.auth.permissions import require_tab, require_action
from app.models.trip import Trip
from app.models.vehicle import Vehicle
from app.models.user import User
from app.models.external_driver import ExternalDriver
from app.services.waybill_numbering import generate_waybill_number
from app.models.organization import Organization

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trips", tags=["vehicles"])

# ─────────────────────── Template selector (D-14) ───────────────────────────

VEHICLE_TYPE_TO_TEMPLATE = {
    "car_light":   "trip_light.docx",
    "minivan":     "trip_light.docx",
    "quadbike":    "trip_light.docx",
    "other":       "trip_light.docx",
    "truck_van":   "trip_truck.docx",
    "truck_board": "trip_truck.docx",
    "truck_tank":  "trip_truck.docx",
    "truck_metal": "trip_truck.docx",
    "bus":         "trip_special.docx",
    "special":     "trip_special.docx",
    "snowmobile":  "trip_special.docx",
    "boat":        "trip_special.docx",
    "boat_motor":  "trip_special.docx",
    "trailer":     "trip_special.docx",
}

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates")


def _get_trip_template_path(vehicle_type: Optional[str]) -> str:
    tpl_name = VEHICLE_TYPE_TO_TEMPLATE.get(vehicle_type or "", "trip_light.docx")
    return os.path.join(TEMPLATES_DIR, tpl_name)


# ─────────────────────── Date helpers ───────────────────────────────────────

_DATE_FIELDS = {"date"}


def _fmt_date(d) -> str:
    if d is None:
        return ""
    if hasattr(d, "strftime"):
        return d.strftime("%d.%m.%Y")
    return str(d)


def _coerce_date(value):
    """Parse ISO date string → date object, or pass through if already date."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value if isinstance(value, date) else value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


# ─────────────────────── Context builder ────────────────────────────────────

def _build_trip_context(
    trip: Trip,
    vehicle: Vehicle,
    driver,
    org: Optional[Organization],
) -> dict:
    """Build docxtpl render context for all 3 trip templates (29-20 extended).

    driver is either User (штатный) or ExternalDriver (внешний) or None.
    All values are str to avoid docxtpl coercion issues.
    """
    # Driver fields
    if driver is None:
        driver_full_name = ""
        driver_license_series = ""
        driver_license_number = ""
        driver_license_categories = ""
        driver_license_issued_at = ""
        driver_license_expires_at = ""
    elif isinstance(driver, User):
        driver_full_name = driver.full_name or ""
        driver_license_series = driver.license_series or ""
        driver_license_number = driver.license_number or ""
        driver_license_categories = driver.license_categories or ""
        driver_license_issued_at = _fmt_date(getattr(driver, "license_issued_at", None))
        driver_license_expires_at = _fmt_date(getattr(driver, "license_expires_at", None))
    else:
        # ExternalDriver
        driver_full_name = driver.full_name or ""
        driver_license_series = driver.license_series or ""
        driver_license_number = driver.license_number or ""
        driver_license_categories = driver.license_categories or ""
        driver_license_issued_at = _fmt_date(driver.license_issued_at)
        driver_license_expires_at = _fmt_date(driver.license_expires_at)

    # Odometer delta
    odo_start = trip.odometer_start or 0
    odo_finish = trip.odometer_finish or 0
    delta_km = max(0, odo_finish - odo_start)

    # Vehicle brand+model
    brand = vehicle.brand or ""
    model = vehicle.model or ""
    vehicle_brand_model = f"{brand} {model}".strip() if (brand or model) else ""

    # Route summary (for forms that have a single 'route' field)
    route_from = trip.route_from or ""
    route_to = trip.route_to or ""
    route = f"{route_from} → {route_to}".strip(" →") if (route_from or route_to) else ""

    # Org
    org_name = (org.name if org else "") or ""
    org_address = (getattr(org, "address", None) if org else None) or ""

    # Vehicle type label (human-readable, 29-20)
    _VEHICLE_TYPE_LABELS = {
        "car_light":   "Легковой автомобиль",
        "minivan":     "Минивэн",
        "quadbike":    "Квадроцикл",
        "truck_van":   "Грузовой (фургон)",
        "truck_board": "Грузовой (бортовой)",
        "truck_tank":  "Грузовой (цистерна)",
        "truck_metal": "Грузовой (металловоз)",
        "bus":         "Автобус",
        "special":     "Спецтехника",
        "snowmobile":  "Снегоход",
        "boat":        "Лодка (весельная)",
        "boat_motor":  "Лодка (моторная)",
        "trailer":     "Прицеп",
        "other":       "Прочее",
    }
    vehicle_type_label = _VEHICLE_TYPE_LABELS.get(vehicle.type or "", vehicle.type or "")

    # Fuel norm & season (29-20: летняя / зимняя)
    trip_date_obj = trip.date if hasattr(trip.date, "month") else None
    if trip_date_obj:
        month = trip_date_obj.month
        fuel_season = "летняя" if 5 <= month <= 9 else "зимняя"
    else:
        fuel_season = "летняя"
    # fuel_norm: from vehicle props if available, else 0
    fuel_norm = float(getattr(vehicle, "fuel_consumption_per_100km", None) or 0)
    fuel_used_calc = round(delta_km * fuel_norm / 100, 2) if fuel_norm else ""

    return {
        # Vehicle
        "vehicle_brand_model":  vehicle_brand_model,
        "vehicle_brand":        brand,
        "vehicle_model":        model,
        "vehicle_type_label":   vehicle_type_label,
        "plate":                vehicle.plate or "",
        "vehicle_color":        vehicle.color or "",
        "fuel_type":            vehicle.fuel_type or "",
        "vehicle_load_capacity": str(getattr(vehicle, "load_capacity_t", None) or ""),
        # Trip
        "trip_number":          f"VSKS-{trip.id:05d}",
        "trip_date":            _fmt_date(trip.date),
        "date":                 _fmt_date(trip.date),
        "date_dmy":             _fmt_date(trip.date),
        # Route
        "route_from":           route_from,
        "route_to":             route_to,
        "route":                route,
        # Odometer
        "odometer_start":       str(odo_start),
        "odometer_finish":      str(odo_finish),
        "delta_km":             str(delta_km),
        "mileage":              str(delta_km),
        "odometer_diff":        str(delta_km),
        # Fuel (29-20 extended)
        "fuel_brand":           vehicle.fuel_type or "",
        "fuel_start":           str(trip.fuel_remaining_start or ""),
        "fuel_finish":          str(trip.fuel_remaining_finish or ""),
        "fuel_remaining_start": str(trip.fuel_remaining_start or ""),
        "fuel_remaining_finish": str(trip.fuel_remaining_finish or ""),
        "fuel_issued_l":        str(trip.fuel_issued_l or ""),
        "fuel_added":           str(trip.fuel_issued_l or ""),
        "fuel_norm":            str(fuel_norm) if fuel_norm else "",
        "fuel_season":          fuel_season,
        "fuel_used_calc":       str(fuel_used_calc) if fuel_used_calc != "" else "",
        # Cargo (truck templates)
        "cargo_name":           trip.cargo_name or "",
        "cargo_weight_t":       str(trip.cargo_weight_t or ""),
        "cargo_count":          "",
        "loading_point":        route_from,
        "unloading_point":      route_to,
        # Driver
        "driver_full_name":          driver_full_name,
        "driver_license_series":     driver_license_series,
        "driver_license_number":     driver_license_number,
        "driver_license_categories": driver_license_categories,
        "driver_license_issued_at":  driver_license_issued_at,
        "driver_license_expires_at": driver_license_expires_at,
        # Purpose / customer / task
        "customer_text":        trip.purpose or "",
        "purpose":              trip.purpose or "",
        "task_description":     "",
        # Org / initiator
        "org_name":             org_name,
        "org_address":          org_address,
        "customer_org_name":    org_name,
        "customer_org_address": org_address,
        "initiator_full_name":  org_name,
        "initiator_position":   "",
    }


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
        raise HTTPException(422, detail={"code": "VEHICLE_REQUIRED", "message": "vehicle_id обязателен"})

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


# ─────────────────────── POST /api/trips/{trip_id}/render ───────────────────

@router.post("/{trip_id}/render")
async def render_trip(
    trip_id: int,
    current_user: User = Depends(require_action("vehicle.trip.create")),
    db: AsyncSession = Depends(get_db),
):
    from docxtpl import DocxTemplate

    trip = await _load_trip_or_404(trip_id, db)
    vehicle = trip.vehicle
    if not _can_see_vehicle(vehicle, current_user):
        raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Нет доступа к этому ТС"})

    # Resolve driver
    if trip.driver_user_id:
        driver = await db.get(User, trip.driver_user_id)
    elif trip.driver_external_id:
        driver = await db.get(ExternalDriver, trip.driver_external_id)
    else:
        driver = None

    # Resolve org
    org = await db.get(Organization, vehicle.owner_org_id) if vehicle.owner_org_id else None

    template_path = _get_trip_template_path(vehicle.type)
    if not os.path.exists(template_path):
        raise HTTPException(500, detail={
            "code": "TEMPLATE_MISSING",
            "message": f"Шаблон путёвки не найден: {os.path.basename(template_path)}",
        })

    try:
        tpl = DocxTemplate(template_path)
        ctx = _build_trip_context(trip, vehicle, driver, org)
        tpl.render(ctx)
        buf = BytesIO()
        tpl.save(buf)
        buf.seek(0)
    except Exception as e:
        raise HTTPException(500, detail={
            "code": "TEMPLATE_RENDER_ERROR",
            "message": "Ошибка генерации путёвки",
            "error_class": e.__class__.__name__,
            "error_raw": str(e),
            "traceback": traceback.format_exc()[-1500:],
            "hint": "Проверьте Lessons 2026-05-15: {% tr %} запрещён",
        })

    # Mark rendered
    trip.status = "rendered"
    await db.commit()

    filename = f"trip_{trip_id}_{trip.date.isoformat()}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────── Internal helpers ───────────────────────────────────

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
    }
