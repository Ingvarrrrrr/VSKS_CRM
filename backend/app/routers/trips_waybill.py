"""
Trips — печать путевого листа: legacy docxtpl-render + .docx/.xlsx выгрузки
(D-14, D-19).

Сосед app/routers/trips.py (Правило №5, резка монолита, сессия 2026-09-08).
ПЕРЕНЕСЕНО без изменений. Тот же префикс /api/trips. Все пути здесь
трёхсегментные (/{trip_id}/...), catch-all ядра GET /{trip_id} им не
конфликтует — порядок регистрации в app/routes.py относительно ядра не важен.

Использует _can_see_vehicle / _load_trip_or_404 из ядра (app.routers.trips) —
не дублирует их (Правило №6).

Template selector (D-14):
  car_light / minivan / quadbike / other  → trip_light.docx  (форма 3)
  truck_*                                 → trip_truck.docx   (форма 4-С)
  bus / special / snowmobile / boat /
    boat_motor / trailer                  → trip_special.docx

Endpoints:
  POST /api/trips/{trip_id}/render         — legacy docxtpl-рендер (D-14, D-19)
  GET  /api/trips/{trip_id}/waybill.docx   — Минтранс №3 .docx (Phase 30-PR3)
  GET  /api/trips/{trip_id}/waybill.xlsx   — форма ВСКС .xlsx (Phase 30.1)
"""
import os
import traceback
from io import BytesIO
from typing import Optional
from urllib.parse import quote as _url_quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth.permissions import require_tab, require_action
from app.models.trip import Trip
from app.models.vehicle import Vehicle
from app.models.user import User
from app.models.external_driver import ExternalDriver
from app.models.organization import Organization
from app.routers.trips import _can_see_vehicle, _load_trip_or_404

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

def _fmt_date(d) -> str:
    if d is None:
        return ""
    if hasattr(d, "strftime"):
        return d.strftime("%d.%m.%Y")
    return str(d)


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

    _trip_date_str = trip.date.isoformat() if trip.date else str(trip_id)
    filename = f"Поездка_{_trip_date_str}_{trip_id}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_url_quote(filename, safe='-_.~')}"},
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

    filename = f"Путевой_лист_{waybill.number or waybill.id}.docx"
    return StreamingResponse(
        BytesIO(bytes_data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_url_quote(filename, safe='-_.~')}"},
    )


# ─────────────────────── GET /{trip_id}/waybill.xlsx (ВСКС форма) ────────────

@router.get("/{trip_id}/waybill.xlsx")
async def download_waybill_xlsx(
    trip_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """
    Скачать путевой лист ВСКС в формате .xlsx (Phase 30.1).

    Альтернативный формат — форма ВСКС на основе xlsx-шаблона.
    Минимальная разметка: номер ПЛ, дата, гос.номер, водитель, марка ТС.
    TODO: полная coordinates-разметка — все поля медосмотра/одометра/топлива.
    """
    from app.services.waybill_xlsx import render_waybill_xlsx_vsks

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
        bytes_data = await render_waybill_xlsx_vsks(waybill, db)
    except FileNotFoundError as e:
        raise HTTPException(500, detail={"code": "TEMPLATE_MISSING", "message": str(e)})
    except Exception as e:
        raise HTTPException(500, detail={
            "code": "WAYBILL_XLSX_RENDER_ERROR",
            "message": str(e),
            "error_class": e.__class__.__name__,
        })

    filename = f"Путевой_лист_{waybill.number or waybill.id}_ВСКС.xlsx"
    return StreamingResponse(
        BytesIO(bytes_data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_url_quote(filename, safe='-_.~')}"},
    )
