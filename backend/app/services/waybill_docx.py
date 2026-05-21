"""
Генерация .docx путевого листа Минтранс №3 через docxtpl.

Подпись водителя — InlineImage из data-url,
подписи механика/медика — пустые линии для рукописной подписи на распечатанном документе.

Phase 30-PR3.
"""
import base64
import logging
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)

# Путь к шаблону — работает как из Docker (/app/...) так и локально
_TEMPLATE_CANDIDATES = [
    Path("/app/backend/templates/waybill_form_3.docx"),
    Path(__file__).parent.parent.parent / "templates" / "waybill_form_3.docx",
]


def _get_template_path() -> Path:
    for p in _TEMPLATE_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Шаблон waybill_form_3.docx не найден. Проверенные пути: {[str(p) for p in _TEMPLATE_CANDIDATES]}"
    )


async def render_waybill_docx(waybill, db) -> bytes:
    """Рендерит путевой лист в .docx по шаблону Минтранс №3.

    waybill = Trip ORM объект (или SimpleNamespace для smoke-тестов).
    db = AsyncSession (может быть None при smoke-тесте без FK полей).
    Возвращает bytes .docx файла.
    """
    try:
        from docxtpl import DocxTemplate, InlineImage
        from docx.shared import Mm
    except ImportError as e:
        raise RuntimeError(f"docxtpl/python-docx не установлены: {e}")

    template_path = _get_template_path()
    tpl = DocxTemplate(str(template_path))

    # ── Форматирование дат ──────────────────────────────────────────────────
    def fmt_date(d, fmt="%d.%m.%Y"):
        if d is None:
            return ""
        if hasattr(d, "strftime"):
            return d.strftime(fmt)
        return str(d)

    def fmt_time(d):
        return fmt_date(d, "%H:%M")

    def fmt_datetime(d):
        return fmt_date(d, "%d.%m.%Y %H:%M")

    # ── Остановки маршрута ──────────────────────────────────────────────────
    route_stops_ctx = []
    for s in (waybill.route_stops or []):
        route_stops_ctx.append({
            "ord": s.ord,
            "name": s.name,
            "planned_time": fmt_time(getattr(s, "planned_time", None)),
            "actual_time": fmt_time(getattr(s, "actual_time", None)),
        })

    # ── Vehicle ─────────────────────────────────────────────────────────────
    vehicle = waybill.vehicle
    vehicle_brand_model = ""
    vehicle_plate = ""
    vehicle_vin = ""
    if vehicle:
        brand = getattr(vehicle, "brand", "") or ""
        model = getattr(vehicle, "model", "") or ""
        vehicle_brand_model = f"{brand} {model}".strip()
        vehicle_plate = getattr(vehicle, "plate", "") or ""
        vehicle_vin = getattr(vehicle, "vin", "") or ""

    # ── Driver ──────────────────────────────────────────────────────────────
    driver_full_name = ""
    driver_license_categories = ""
    driver_license_number = ""
    driver_tab_number = ""
    driver_user = waybill.driver_user if hasattr(waybill, "driver_user") else None
    if driver_user:
        driver_full_name = getattr(driver_user, "full_name", "") or ""
        driver_license_categories = getattr(driver_user, "license_categories", "") or ""
        driver_license_number = getattr(driver_user, "license_number", "") or ""
        driver_tab_number = getattr(driver_user, "driver_tab_number", "") or ""

    # ── Org ─────────────────────────────────────────────────────────────────
    org_name = ""
    org_address = ""
    if vehicle:
        org = getattr(vehicle, "assigned_org", None) or getattr(vehicle, "owner_org", None)
        if org:
            org_name = getattr(org, "name", "") or ""
            org_address = getattr(org, "address", "") or ""

    # ── Подпись водителя ─────────────────────────────────────────────────────
    driver_sig_raw = getattr(waybill, "driver_signature", None)
    if driver_sig_raw and isinstance(driver_sig_raw, str) and driver_sig_raw.startswith("data:image/"):
        try:
            _header, b64 = driver_sig_raw.split(",", 1)
            png_bytes = base64.b64decode(b64)
            tmp = BytesIO(png_bytes)
            driver_signature_image = InlineImage(tpl, tmp, width=Mm(50))
        except Exception as e:
            logger.warning(f"Не удалось декодировать подпись водителя: {e}")
            driver_signature_image = "___________"
    else:
        driver_signature_image = "___________"

    # ── Имена механика/медика через DB lookup ────────────────────────────────
    async def _resolve_name(uid: int | None) -> str:
        if uid is None or db is None:
            return ""
        try:
            from app.models.user import User
            from sqlalchemy import select
            res = await db.execute(select(User).where(User.id == uid))
            u = res.scalars().first()
            return (u.full_name if u else "") or ""
        except Exception as e:
            logger.warning(f"Не удалось разрешить имя пользователя id={uid}: {e}")
            return ""

    pre_trip_mechanic_name = await _resolve_name(getattr(waybill, "pre_trip_mechanic_id", None))
    pre_trip_doctor_name = await _resolve_name(getattr(waybill, "pre_trip_doctor_id", None))
    post_trip_mechanic_name = await _resolve_name(getattr(waybill, "post_trip_mechanic_id", None))
    post_trip_doctor_name = await _resolve_name(getattr(waybill, "post_trip_doctor_id", None))

    # ── Context dict ─────────────────────────────────────────────────────────
    ctx = {
        # Идентификация
        "waybill_number": getattr(waybill, "number", None) or f"TMP-{getattr(waybill, 'id', 0)}",
        "waybill_date": fmt_date(getattr(waybill, "date_start", None) or getattr(waybill, "date", None)),
        # Организация
        "org_name": org_name,
        "org_address": org_address,
        # Транспортное средство
        "vehicle_brand_model": vehicle_brand_model,
        "vehicle_plate": vehicle_plate,
        "vehicle_garage_number": "",
        "vehicle_vin": vehicle_vin,
        # Водитель
        "driver_full_name": driver_full_name,
        "driver_license_categories": driver_license_categories,
        "driver_license_number": driver_license_number,
        "driver_tab_number": driver_tab_number,
        "driver_signature_image": driver_signature_image,
        "driver_signed_at": fmt_datetime(getattr(waybill, "driver_signed_at", None)),
        # Маршрут (список для {% for %} в шаблоне)
        "route_stops": route_stops_ctx,
        # Задание
        "task_description": getattr(waybill, "purpose", None) or "",
        "cargo_description": getattr(waybill, "cargo_description", None) or getattr(waybill, "cargo_name", None) or "",
        "passengers_count": getattr(waybill, "passengers_count", None) or 0,
        # Километраж
        "planned_mileage_km": getattr(waybill, "planned_mileage_km", None) or 0,
        "actual_mileage_km": getattr(waybill, "actual_mileage_km", None) or 0,
        "odometer_start": getattr(waybill, "odometer_start", None) or 0,
        "odometer_finish": getattr(waybill, "odometer_finish", None) or 0,
        # Топливо
        "fuel_start": getattr(waybill, "fuel_remaining_start", None) or 0,
        "fuel_end": getattr(waybill, "fuel_remaining_finish", None) or 0,
        "fuel_issued": getattr(waybill, "fuel_issued_l", None) or 0,
        # Пред-рейсовый механик
        "pre_trip_mechanic_name": pre_trip_mechanic_name,
        "pre_trip_mechanic_inspected_at": fmt_time(getattr(waybill, "pre_trip_mechanic_inspected_at", None)),
        "pre_trip_mechanic_result": getattr(waybill, "pre_trip_mechanic_result", None) or "",
        # Пред-рейсовый медик
        "pre_trip_doctor_name": pre_trip_doctor_name,
        "pre_trip_doctor_inspected_at": fmt_time(getattr(waybill, "pre_trip_doctor_inspected_at", None)),
        "pre_trip_doctor_result": getattr(waybill, "pre_trip_doctor_result", None) or "",
        # Пост-рейсовый механик
        "post_trip_mechanic_name": post_trip_mechanic_name,
        "post_trip_mechanic_inspected_at": fmt_time(getattr(waybill, "post_trip_mechanic_inspected_at", None)),
        "post_trip_mechanic_result": getattr(waybill, "post_trip_mechanic_result", None) or "",
        # Пост-рейсовый медик
        "post_trip_doctor_name": post_trip_doctor_name,
        "post_trip_doctor_inspected_at": fmt_time(getattr(waybill, "post_trip_doctor_inspected_at", None)),
        "post_trip_doctor_result": getattr(waybill, "post_trip_doctor_result", None) or "",
    }

    tpl.render(ctx)
    out = BytesIO()
    tpl.save(out)
    out.seek(0)
    return out.read()
