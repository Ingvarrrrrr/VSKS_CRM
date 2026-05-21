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
from app.models.waybill_children import RouteStop, OdometerReading, FuelRefill
from app.schemas.waybill_workflow import (
    TechInspectIn, MedInspectIn, PostTripMechanicIn, PostTripDoctorIn,
    DriverSignIn, RouteStopIn, OdometerReadingIn, FuelRefillIn,
)

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


# ─────────────────────── GET /{trip_id}/waybill.docx ────────────────────────

@router.get("/{trip_id}/waybill.docx")
async def download_waybill_docx(
    trip_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Скачать путевой лист Минтранс №3 в формате .docx (Phase 30-PR3).

    Включает InlineImage подписи водителя и пустые линии для рукописных подписей
    механика/медика.
    """
    from app.services.waybill_docx import render_waybill_docx

    result = await db.execute(
        select(Trip)
        .options(
            selectinload(Trip.vehicle),
            selectinload(Trip.driver_user),
            selectinload(Trip.route_stops),
        )
        .where(Trip.id == trip_id)
    )
    waybill = result.scalars().first()
    if not waybill:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Путевой лист не найден"})

    if not _can_see_vehicle(waybill.vehicle, current_user):
        raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Нет доступа к этому ТС"})

    try:
        bytes_data = await render_waybill_docx(waybill, db)
    except FileNotFoundError as e:
        raise HTTPException(500, detail={"code": "TEMPLATE_MISSING", "message": str(e)})
    except Exception as e:
        raise HTTPException(500, detail={
            "code": "WAYBILL_RENDER_ERROR",
            "message": str(e),
            "error_class": e.__class__.__name__,
        })

    filename = f"waybill_{waybill.number or waybill.id}.docx"
    return StreamingResponse(
        BytesIO(bytes_data),
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


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 30-PR3: Workflow status transition endpoints
# ═══════════════════════════════════════════════════════════════════════════════

# Allowed status transitions map
_ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "created":      ["tech_inspect"],
    "draft":        ["tech_inspect"],  # legacy alias
    "tech_inspect": ["med_inspect"],
    "med_inspect":  ["in_progress"],
    "in_progress":  ["on_review"],    # via driver-sign
    "on_review":    ["closed"],
    # Terminal states — no outgoing transitions
    "closing":      [],
    "closed":       [],
    "overdue":      [],
    "rendered":     [],               # legacy
}


def _assert_status_transition(current: str, target: str) -> None:
    """Raise 422 if the transition from current → target is not allowed."""
    allowed = _ALLOWED_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_STATUS_TRANSITION",
                "message": f"Нельзя перевести из «{current}» в «{target}». "
                           f"Разрешённые переходы из «{current}»: {allowed or 'нет (конечный статус)'}",
            },
        )


# ─────────────────────── POST /{trip_id}/tech-inspect ───────────────────────

@router.post("/{trip_id}/tech-inspect")
async def tech_inspect(
    trip_id: int,
    body: TechInspectIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Механик подтверждает тех. осмотр (pre-trip). Status: created → med_inspect."""
    trip = await _load_trip_or_404(trip_id, db)
    _assert_status_transition(trip.status, "tech_inspect")

    mechanic = await db.get(User, body.mechanic_id)
    if not mechanic:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Механик не найден"})

    trip.pre_trip_mechanic_id = body.mechanic_id
    trip.pre_trip_mechanic_inspected_at = body.inspected_at
    trip.pre_trip_mechanic_result = body.result
    trip.status = "med_inspect"

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── POST /{trip_id}/med-inspect ────────────────────────

@router.post("/{trip_id}/med-inspect")
async def med_inspect(
    trip_id: int,
    body: MedInspectIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Медик подтверждает медосмотр (pre-trip). Status: med_inspect → in_progress."""
    trip = await _load_trip_or_404(trip_id, db)
    _assert_status_transition(trip.status, "med_inspect")

    doctor = await db.get(User, body.doctor_id)
    if not doctor:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Медик не найден"})

    trip.pre_trip_doctor_id = body.doctor_id
    trip.pre_trip_doctor_inspected_at = body.inspected_at
    trip.pre_trip_doctor_result = body.result
    trip.status = "in_progress"

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── POST /{trip_id}/post-trip-mechanic ─────────────────

@router.post("/{trip_id}/post-trip-mechanic")
async def post_trip_mechanic(
    trip_id: int,
    body: PostTripMechanicIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Послерейсовый механик. Фиксирует осмотр, статус НЕ меняется."""
    trip = await _load_trip_or_404(trip_id, db)

    mechanic = await db.get(User, body.mechanic_id)
    if not mechanic:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Механик не найден"})

    trip.post_trip_mechanic_id = body.mechanic_id
    trip.post_trip_mechanic_inspected_at = body.inspected_at
    trip.post_trip_mechanic_result = body.result

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── POST /{trip_id}/post-trip-doctor ───────────────────

@router.post("/{trip_id}/post-trip-doctor")
async def post_trip_doctor(
    trip_id: int,
    body: PostTripDoctorIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Послерейсовый медик. Фиксирует осмотр, статус НЕ меняется."""
    trip = await _load_trip_or_404(trip_id, db)

    doctor = await db.get(User, body.doctor_id)
    if not doctor:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Медик не найден"})

    trip.post_trip_doctor_id = body.doctor_id
    trip.post_trip_doctor_inspected_at = body.inspected_at
    trip.post_trip_doctor_result = body.result

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── POST /{trip_id}/driver-sign ────────────────────────

@router.post("/{trip_id}/driver-sign")
async def driver_sign(
    trip_id: int,
    body: DriverSignIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Водитель ставит электронную подпись. Status: in_progress → on_review."""
    trip = await _load_trip_or_404(trip_id, db)
    _assert_status_transition(trip.status, "on_review")

    if not body.signature:
        raise HTTPException(422, detail={"code": "SIGNATURE_REQUIRED", "message": "Подпись обязательна"})

    trip.driver_signature = body.signature
    trip.driver_signed_at = body.signed_at
    trip.status = "on_review"

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── POST /{trip_id}/close ──────────────────────────────

@router.post("/{trip_id}/close")
async def close_waybill(
    trip_id: int,
    current_user: User = Depends(require_action("vehicle.trip.create")),
    db: AsyncSession = Depends(get_db),
):
    """Диспетчер закрывает путевой лист. Status: on_review → closed."""
    trip = await _load_trip_or_404(trip_id, db)
    _assert_status_transition(trip.status, "closed")

    trip.status = "closed"

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


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


