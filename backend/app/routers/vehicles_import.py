"""
vehicles_import router — Plan 29-12, Phase 29 «Имущество → Автотранспорт».

UI Excel upload + region→org mapping dialog.

Endpoints:
  POST /api/vehicles-import/preview           — parse xlsx, return preview + unmapped regions
  GET  /api/vehicles-import/preview/{sid}     — re-fetch preview by session_id
  POST /api/vehicles-import/commit            — apply region_mapping and INSERT vehicles
  GET  /api/vehicles-import/regions/unmapped  — list existing assigned_text without org

Decisions covered: D-06, D-09

Разрезание (Правило №5, 2026-09-08): парсинг xlsx (column-mapping spec,
коэрсеры значений, сама функция разбора) и сопоставление организаций/сборка
preview-ответа вынесены в app/services/fleet_import_*.py — этот файл теперь
только сессии предпросмотра + сами HTTP-эндпоинты:
  - fleet_import_columns.py  — заголовки xlsx → поля Vehicle (_COL_MAP и пр.)
  - fleet_import_coerce.py   — коэрсия значений ячеек
  - fleet_import_parser.py   — _parse_xlsx_to_rows (байты → список строк)
  - fleet_import_matching.py — сопоставление организаций + _build_preview_payload
Генератор шаблона для скачивания (GET /api/vehicles/import-template, ниже) уже
жил в app/services/vehicle_import_template.py до этого разрезания — не тронут.
"""
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from urllib.parse import quote as _url_quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_action, require_tab
from app.database import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.vehicle_fields import get_hidden_field_keys
from app.services.vehicle_import_template import build_vehicle_import_template
from app.services.vehicle_org_matching import resolve_org_for_text
from app.services.fleet_import_columns import _DATE_COLS
from app.services.fleet_import_matching import (
    _apply_row_passes,
    _build_org_indexes,
    _build_preview_payload,
)
from app.services.fleet_import_parser import _parse_xlsx_to_rows

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vehicles-import", tags=["vehicles-import"])

# ─────────────────────────── In-memory session store ────────────────────────

_IMPORT_SESSIONS: Dict[str, dict] = {}
_SESSION_TTL = timedelta(minutes=30)


def _cleanup_old_sessions() -> None:
    """Remove sessions older than TTL and delete their tmp files."""
    cutoff = datetime.now(timezone.utc) - _SESSION_TTL
    expired = [sid for sid, s in _IMPORT_SESSIONS.items() if s["created_at"] < cutoff]
    for sid in expired:
        tmp = _IMPORT_SESSIONS[sid].get("tmp_path")
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        del _IMPORT_SESSIONS[sid]


@router.post("/preview")
async def preview_import(
    file: UploadFile = File(...),
    current_user: User = Depends(require_action("vehicle.import")),
    db: AsyncSession = Depends(get_db),
):
    """Parse uploaded xlsx, return preview + unmapped region list."""
    _cleanup_old_sessions()

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=422,
            detail={"msg": "Ожидается файл .xlsx", "code": "bad_extension"},
        )

    raw_bytes = await file.read()
    if len(raw_bytes) == 0:
        raise HTTPException(
            status_code=422,
            detail={"msg": "Файл пустой", "code": "empty_file"},
        )

    # Save to temp file (needed for commit step)
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    try:
        tmp_file.write(raw_bytes)
        tmp_file.flush()
        tmp_path = tmp_file.name
    finally:
        tmp_file.close()

    parsed_rows, warnings = _parse_xlsx_to_rows(raw_bytes)
    inn_index, name_index = await _build_org_indexes(db)

    session_id = str(uuid.uuid4())
    _IMPORT_SESSIONS[session_id] = {
        "tmp_path": tmp_path,
        "created_at": datetime.now(timezone.utc),
        "parsed_rows": parsed_rows,
        "user_id": current_user.id,
    }

    payload = _build_preview_payload(parsed_rows, inn_index, name_index)
    payload["session_id"] = session_id
    payload["warnings"] = warnings
    return payload


# ─────────────────────────── GET /preview/{session_id} ───────────────────────

@router.get("/preview/{session_id}")
async def get_preview(
    session_id: str,
    current_user: User = Depends(require_action("vehicle.import")),
    db: AsyncSession = Depends(get_db),
):
    """Re-fetch preview data for an existing session."""
    _cleanup_old_sessions()
    session = _IMPORT_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={"msg": "Сессия не найдена или истекла (30 мин)", "code": "session_not_found"},
        )
    if session["user_id"] != current_user.id and current_user.role not in ("superadmin", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"msg": "Сессия принадлежит другому пользователю", "code": "session_forbidden"},
        )

    inn_index, name_index = await _build_org_indexes(db)
    parsed_rows = session["parsed_rows"]

    payload = _build_preview_payload(parsed_rows, inn_index, name_index)
    payload["session_id"] = session_id
    return payload


# ─────────────────────────── POST /commit ────────────────────────────────────

class CommitBody(BaseModel):
    session_id: str
    region_mapping: Dict[str, int] = {}          # assigned_text → org_id
    owner_mapping: Dict[str, int] = {}           # owner_text → org_id
    default_owner_org_id: Optional[int] = None   # fallback owner org
    conflict_strategy: str = "skip"              # "skip" | "update"


@router.post("/commit")
async def commit_import(
    body: CommitBody,
    current_user: User = Depends(require_action("vehicle.import")),
    db: AsyncSession = Depends(get_db),
):
    """Apply region_mapping and insert/update vehicles from session."""
    _cleanup_old_sessions()

    session = _IMPORT_SESSIONS.get(body.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={"msg": "Сессия не найдена или истекла (30 мин)", "code": "session_not_found"},
        )
    if session["user_id"] != current_user.id and current_user.role not in ("superadmin", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"msg": "Сессия принадлежит другому пользователю", "code": "session_forbidden"},
        )

    if body.conflict_strategy not in ("skip", "update"):
        raise HTTPException(
            status_code=422,
            detail={"msg": "conflict_strategy должна быть 'skip' или 'update'", "code": "bad_strategy"},
        )

    inn_index, name_index = await _build_org_indexes(db)
    parsed_rows = session["parsed_rows"]
    valid_rows = [r for r in parsed_rows if not r.get("_skip")]

    # Merge region_mapping with auto-detected org matches
    combined_region_map: Dict[str, int] = dict(body.region_mapping)
    combined_owner_map: Dict[str, int] = dict(body.owner_mapping)

    inserted = 0
    updated = 0
    skipped = 0
    errors: list[dict] = []

    # Строки с row["_state_unrecognized"] (см. _parse_xlsx_to_rows) требуют
    # ПОСТ-INSERT коррекции state=NULL: Vehicle.state объявлен с client-side
    # Column(default="working") — SQLAlchemy применяет такой default, если
    # резолвленное значение колонки на момент flush есть None, ВНЕ
    # зависимости от того, было ли оно явно присвоено или атрибут вовсе не
    # трогали (see Lesson 2026-08-31: простое fields["state"]=None не
    # помогает, INSERT всё равно уйдёт со state='working'). default
    # срабатывает только на INSERT, не на UPDATE — поэтому для новых записей
    # object добавляется в pending_null_state и получает "state = None"
    # ПОСЛЕ первого flush (когда INSERT уже прошёл с дефолтом), что уходит
    # отдельным UPDATE. Для уже существующих (conflict_strategy="update")
    # объект persistent и default не участвует — присваиваем сразу.
    pending_null_state: list[Vehicle] = []
    # 2026-09: (vehicle, row["passes"]) для строк, где найдены колонки "Пропуск: ...".
    # Обрабатываются ПОСЛЕ основного цикла (см. _apply_row_passes ниже) — для новых
    # машин vehicle.id появляется только после db.flush().
    pending_passes: list[tuple[Vehicle, dict]] = []

    _VEHICLE_FIELDS = {
        "brand", "model", "color", "vin", "plate", "type", "state",
        "fuel_type", "fuel_norm_summer", "fuel_norm_winter", "next_to_km",
        "has_tracker", "akb_ok", "has_radio", "mirrors_ok",
        "has_keys", "has_first_aid_kit", "has_spare_wheel", "has_extinguisher",
        "registered_at", "insurance_until",
        # Автоблок: полный реестр полей ТС (AUTOBLOCK_FIELDS_SPEC.md §1) —
        # только "column"-хранимые; props-хранимые (_PROPS_KEYS) собираются
        # отдельно в row["props"] и мержатся в vehicles.props ниже.
        "year_of_manufacture", "last_to_mileage_km", "last_to_date",
        "pts_number", "sts_number", "tech_inspection_until", "purchase_info",
        "assignment_basis", "assignment_doc_number", "assignment_doc_date",
        "engine_power_hp", "engine_volume_l",
        "body_type", "pts_category",
        "insurance_company", "insurance_policy_number",
        "ownership_basis", "ownership_doc_number", "ownership_doc_date", "owner_since",
        "location_city", "location_address", "home_base_city", "responsible_name",
        "pts_kind", "sts_issued_at",
        "tech_inspection_status", "tech_inspection_last_date",
        # 2026-09: pass_* убраны — единственный источник правды теперь
        # vehicle_passes (см. row["passes"] / _apply_row_passes ниже).
        "has_spare_tires", "tires_condition", "has_mirrors",
        "first_aid_kit_until", "extinguisher_check_date", "tracker_paid_until",
        "has_tachograph", "tachograph_check_date",
        "repair_required", "tech_condition_info",
        "current_odometer_km",
        # 2026-09: брендирование — признак + резина по сезонным комплектам
        "has_branding",
        "tires_summer_radius", "tires_summer_profile", "tires_summer_condition",
        "tires_winter_radius", "tires_winter_profile", "tires_winter_condition",
    }

    # Автоблок: полный набор date-полей (для конвертации ISO-строки → date).
    # Тот же реестр-производный набор, что и _DATE_COLS модуля — единый источник
    # правды, чтобы не разъезжаться руками (см. _load_date_columns_from_registry).
    _ALL_DATE_FIELDS = _DATE_COLS

    for row in valid_rows:
        plate = row.get("plate")
        row_n = row.get("_row_n", "?")

        try:
            # Resolve owner_org_id: приоритет — ручной выбор пользователя из
            # диалога (owner_mapping, для строк, которые не сопоставились
            # автоматически), затем автоопределение по ИНН/названию. НИКОГДА
            # не подставляем организацию текущего пользователя молча — если
            # ничего не подошло и default_owner_org_id не задан явно, строка
            # уходит в errors (владелец должен доопределить её в диалоге).
            owner_text = row.get("owner_text") or ""
            auto_owner_id, _owner_method = resolve_org_for_text(
                owner_text, row.get("owner_inn"), inn_index, name_index
            )
            owner_org_id: Optional[int] = (
                combined_owner_map.get(owner_text)
                or auto_owner_id
                or body.default_owner_org_id
            )
            if owner_org_id is None:
                errors.append({
                    "row": row_n, "plate": plate,
                    "msg": f"Организация-собственник не определена для «{owner_text or '(пусто)'}» — сопоставьте вручную",
                })
                continue

            # Resolve assigned_org_id — та же логика (ИНН приоритетнее названия),
            # но None допустим (assigned_org_id nullable, остаётся текстовый fallback).
            assigned_text = row.get("assigned_text") or ""
            auto_assigned_id, _assigned_method = resolve_org_for_text(
                assigned_text, row.get("assigned_inn"), inn_index, name_index
            )
            assigned_org_id: Optional[int] = (
                combined_region_map.get(assigned_text)
                or auto_assigned_id
            )

            # Build field dict for Vehicle
            fields: dict[str, Any] = {}
            for f in _VEHICLE_FIELDS:
                val = row.get(f)
                if val is not None:
                    fields[f] = val

            fields["owner_org_id"] = owner_org_id
            fields["assigned_org_id"] = assigned_org_id
            fields["assigned_text"] = assigned_text if assigned_text else None

            # Convert date strings to date objects
            for dcol in _ALL_DATE_FIELDS:
                v = fields.get(dcol)
                if isinstance(v, str) and v:
                    try:
                        from datetime import datetime as _dt
                        fields[dcol] = _dt.strptime(v, "%Y-%m-%d").date()
                    except ValueError:
                        fields.pop(dcol, None)

            # props-хранимые поля (Автоблок §2: tires_type/branding/paint_condition/
            # defect_description/note) — собраны парсером в row["props"], сюда не входят
            # через _VEHICLE_FIELDS (это не колонки Vehicle).
            row_props: dict = row.get("props") or {}

            # Check existing
            existing_result = await db.execute(
                select(Vehicle).where(Vehicle.plate == plate)
            )
            existing: Optional[Vehicle] = existing_result.scalar_one_or_none()

            row_passes: dict = row.get("passes") or {}

            if existing is None:
                if row_props:
                    fields["props"] = row_props
                vehicle = Vehicle(**fields)
                db.add(vehicle)
                inserted += 1
                if row.get("_state_unrecognized"):
                    pending_null_state.append(vehicle)
                if row_passes:
                    pending_passes.append((vehicle, row_passes))
            elif body.conflict_strategy == "update":
                for k, v in fields.items():
                    setattr(existing, k, v)
                if row_props:
                    from sqlalchemy.orm.attributes import flag_modified
                    existing.props = {**(existing.props or {}), **row_props}
                    flag_modified(existing, "props")
                if row.get("_state_unrecognized"):
                    # existing — persistent объект, default тут не участвует
                    # (default применяется только на INSERT) — прямое
                    # присваивание сразу даст корректный UPDATE ... SET state=NULL.
                    existing.state = None
                updated += 1
                if row_passes:
                    pending_passes.append((existing, row_passes))
            else:
                skipped += 1

        except Exception as exc:
            logger.exception("vehicles_import commit row %s error", row_n)
            errors.append({"row": row_n, "plate": plate, "msg": str(exc)})

    if pending_null_state or pending_passes:
        # Первый flush проводит INSERT'ы (Column default="working" неизбежно
        # сработает для этих объектов, плюс новым Vehicle нужен id для FK
        # vehicle_passes.vehicle_id); затем перезаписываем state=None на уже
        # persistent объектах — это уходит отдельным UPDATE, default на него
        # не влияет (см. комментарий у объявления pending_null_state выше).
        await db.flush()
        for vehicle in pending_null_state:
            vehicle.state = None
        for vehicle, row_passes in pending_passes:
            await _apply_row_passes(db, vehicle.id, row_passes)

    await db.commit()

    # Cleanup
    tmp_path = session.get("tmp_path")
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    _IMPORT_SESSIONS.pop(body.session_id, None)

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total_processed": len(valid_rows),
    }


# ─────────────────────────── GET /regions/unmapped ───────────────────────────

@router.get("/regions/unmapped")
async def get_unmapped_regions(
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """List unique assigned_text values without a resolved assigned_org_id."""
    result = await db.execute(
        select(Vehicle.assigned_text)
        .where(
            Vehicle.assigned_text.isnot(None),
            Vehicle.assigned_text != "",
            Vehicle.assigned_org_id.is_(None),
        )
        .distinct()
        .order_by(Vehicle.assigned_text)
    )
    rows = result.scalars().all()
    return {"unmapped_regions": [{"raw_text": r} for r in rows], "count": len(rows)}


# ─────────────────────── GET /api/vehicles/import-template ──────────────────
#
# Отдельный router с prefix="/api/vehicles" (а не "/api/vehicles-import" как у
# основного router этого файла) — так просил владелец задания: путь должен
# жить рядом с остальными /api/vehicles/* эндпоинтами. Регистрируется в
# app/__init__.py ДО vehicles.router — иначе его перехватил бы catch-all
# GET /api/vehicles/{vehicle_id} (там нет `:int`-констрейнта на путь).

vehicles_template_router = APIRouter(prefix="/api/vehicles", tags=["vehicles-import"])


@vehicles_template_router.get("/import-template")
async def download_vehicle_import_template(
    current_user: User = Depends(require_action("vehicle.import")),
    db: AsyncSession = Depends(get_db),
):
    """Скачать шаблон Excel для импорта реестра транспорта (лист «Транспорт» +
    «Инструкция» + «Справочники»). Состав колонок — реестр services/vehicle_fields.py
    за вычетом полей, скрытых для организации текущего пользователя."""
    from fastapi.responses import StreamingResponse

    hidden_keys = await get_hidden_field_keys(db, current_user.org_id)
    try:
        buf = build_vehicle_import_template(hidden_keys)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{_url_quote('Шаблон_импорта_транспорта.xlsx', safe='-_.~')}"
            )
        },
    )

