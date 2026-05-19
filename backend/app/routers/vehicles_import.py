"""
vehicles_import router — Plan 29-12, Phase 29 «Имущество → Автотранспорт».

UI Excel upload + region→org mapping dialog.

Endpoints:
  POST /api/vehicles-import/preview           — parse xlsx, return preview + unmapped regions
  GET  /api/vehicles-import/preview/{sid}     — re-fetch preview by session_id
  POST /api/vehicles-import/commit            — apply region_mapping and INSERT vehicles
  GET  /api/vehicles-import/regions/unmapped  — list existing assigned_text without org

Decisions covered: D-06, D-09
"""
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.permissions import require_action, require_tab
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.vehicle import Vehicle

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


# ─────────────────────────── Column mapping (inline, DRY-able later) ─────────

# Maps XLSX column headers (lowercased, stripped) → Vehicle field name
_COL_MAP: Dict[str, str] = {
    "гос. номер": "plate",
    "гос.номер": "plate",
    "госномер": "plate",
    "гос номер": "plate",
    "регистрационный знак": "plate",
    "марка": "brand",
    "модель": "model",
    "цвет": "color",
    "vin": "vin",
    "тип": "type",
    "состояние": "state",
    "топливо": "fuel_type",
    "вид топлива": "fuel_type",
    "норма лето": "fuel_norm_summer",
    "норма зима": "fuel_norm_winter",
    "следующее то": "next_to_km",
    "у кого в эксплуатации": "assigned_text",
    "кому принадлежит": "owner_text",
    "дата регистрации": "registered_at",
    "страховка до": "insurance_until",
    "трекер": "has_tracker",
    "аккумулятор": "akb_ok",
    "рация": "has_radio",
    "зеркала": "mirrors_ok",
    "ключи": "has_keys",
    "аптечка": "has_first_aid_kit",
    "запаска": "has_spare_wheel",
    "огнетушитель": "has_extinguisher",
}

_BOOL_COLS = {
    "has_tracker", "akb_ok", "has_radio", "mirrors_ok",
    "has_keys", "has_first_aid_kit", "has_spare_wheel", "has_extinguisher",
}
_DATE_COLS = {"registered_at", "insurance_until"}
_FLOAT_COLS = {"fuel_norm_summer", "fuel_norm_winter"}
_INT_COLS = {"next_to_km"}


def _coerce_bool(val: Any) -> Optional[bool]:
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in ("1", "да", "yes", "true", "+"):
        return True
    if s in ("0", "нет", "no", "false", "-"):
        return False
    return None


def _coerce_date(val: Any) -> Optional[str]:
    """Return ISO date string or None."""
    if val is None:
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _parse_xlsx_to_rows(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """Parse xlsx bytes into list of row-dicts and list of warnings.

    Returns (rows, warnings). rows: list of dicts with Vehicle field names.
    """
    try:
        from openpyxl import load_workbook as _lw
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail={"msg": "openpyxl не установлен на сервере", "code": "openpyxl_missing"},
        )

    wb = _lw(BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    # Find header row (first non-empty row)
    header_raw: Optional[tuple] = None
    header_row_idx = 0
    for idx, row in enumerate(rows_iter, start=1):
        if any(c is not None for c in row):
            header_raw = row
            header_row_idx = idx
            break

    if header_raw is None:
        return [], ["Файл не содержит данных"]

    # Build col_index → field_name mapping
    col_field: Dict[int, str] = {}
    for ci, cell in enumerate(header_raw):
        if cell is None:
            continue
        key = str(cell).strip().lower()
        if key in _COL_MAP:
            col_field[ci] = _COL_MAP[key]

    parsed_rows: list[dict] = []
    warnings: list[str] = []
    row_n = header_row_idx

    for raw_row in rows_iter:
        row_n += 1
        if all(c is None for c in raw_row):
            continue  # skip fully empty rows

        row_data: dict[str, Any] = {"_row_n": row_n}
        for ci, field in col_field.items():
            val = raw_row[ci] if ci < len(raw_row) else None
            if field in _BOOL_COLS:
                row_data[field] = _coerce_bool(val)
            elif field in _DATE_COLS:
                row_data[field] = _coerce_date(val)
            elif field in _FLOAT_COLS:
                try:
                    row_data[field] = float(val) if val is not None else None
                except (TypeError, ValueError):
                    row_data[field] = None
            elif field in _INT_COLS:
                try:
                    row_data[field] = int(float(val)) if val is not None else None
                except (TypeError, ValueError):
                    row_data[field] = None
            else:
                row_data[field] = str(val).strip() if val is not None else None

        # plate is mandatory
        plate = row_data.get("plate")
        if not plate:
            warnings.append(f"Строка {row_n}: госномер отсутствует, пропущена")
            row_data["_skip"] = True

        parsed_rows.append(row_data)

    wb.close()
    return parsed_rows, warnings


# ─────────────────────────── Org lookup cache ────────────────────────────────

async def _build_org_lookup(db: AsyncSession) -> Dict[str, int]:
    """Return dict {lowercased org name → org_id}."""
    result = await db.execute(select(Organization.id, Organization.name))
    return {row.name.strip().lower(): row.id for row in result.all() if row.name}


def _match_org(text_val: Optional[str], lookup: Dict[str, int]) -> Optional[int]:
    if not text_val:
        return None
    return lookup.get(text_val.strip().lower())


# ─────────────────────────── POST /preview ───────────────────────────────────

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
    org_lookup = await _build_org_lookup(db)

    valid_rows = [r for r in parsed_rows if not r.get("_skip")]
    invalid_rows = [r for r in parsed_rows if r.get("_skip")]

    # Collect region texts
    assigned_counter: Dict[str, int] = {}
    matched_orgs: Dict[str, dict] = {}
    for row in valid_rows:
        txt = row.get("assigned_text") or ""
        if txt:
            assigned_counter[txt] = assigned_counter.get(txt, 0) + 1
            if txt not in matched_orgs:
                oid = _match_org(txt, org_lookup)
                if oid is not None:
                    matched_orgs[txt] = {"raw_text": txt, "org_id": oid, "org_name": txt}

    unmapped_regions = [
        {"raw_text": txt, "occurrences": cnt}
        for txt, cnt in assigned_counter.items()
        if txt not in matched_orgs
    ]
    matched_list = list(matched_orgs.values())

    preview_items = []
    for row in valid_rows[:10]:
        preview_items.append({
            "row_n": row["_row_n"],
            "plate": row.get("plate"),
            "brand": row.get("brand"),
            "model": row.get("model"),
            "owner_text": row.get("owner_text"),
            "assigned_text": row.get("assigned_text"),
            "type": row.get("type"),
            "state": row.get("state"),
            "fuel_type": row.get("fuel_type"),
        })

    session_id = str(uuid.uuid4())
    _IMPORT_SESSIONS[session_id] = {
        "tmp_path": tmp_path,
        "created_at": datetime.now(timezone.utc),
        "parsed_rows": parsed_rows,
        "user_id": current_user.id,
    }

    return {
        "session_id": session_id,
        "rows_total": len(parsed_rows),
        "rows_valid": len(valid_rows),
        "rows_invalid": len(invalid_rows),
        "unmapped_regions": unmapped_regions,
        "matched_orgs": matched_list,
        "preview_items": preview_items,
        "warnings": warnings,
    }


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

    org_lookup = await _build_org_lookup(db)
    parsed_rows = session["parsed_rows"]
    valid_rows = [r for r in parsed_rows if not r.get("_skip")]
    invalid_rows = [r for r in parsed_rows if r.get("_skip")]

    assigned_counter: Dict[str, int] = {}
    matched_orgs: Dict[str, dict] = {}
    for row in valid_rows:
        txt = row.get("assigned_text") or ""
        if txt:
            assigned_counter[txt] = assigned_counter.get(txt, 0) + 1
            if txt not in matched_orgs:
                oid = _match_org(txt, org_lookup)
                if oid is not None:
                    matched_orgs[txt] = {"raw_text": txt, "org_id": oid, "org_name": txt}

    unmapped_regions = [
        {"raw_text": txt, "occurrences": cnt}
        for txt, cnt in assigned_counter.items()
        if txt not in matched_orgs
    ]

    preview_items = []
    for row in valid_rows[:10]:
        preview_items.append({
            "row_n": row["_row_n"],
            "plate": row.get("plate"),
            "brand": row.get("brand"),
            "model": row.get("model"),
            "owner_text": row.get("owner_text"),
            "assigned_text": row.get("assigned_text"),
        })

    return {
        "session_id": session_id,
        "rows_total": len(parsed_rows),
        "rows_valid": len(valid_rows),
        "rows_invalid": len(invalid_rows),
        "unmapped_regions": unmapped_regions,
        "matched_orgs": list(matched_orgs.values()),
        "preview_items": preview_items,
    }


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

    org_lookup = await _build_org_lookup(db)
    parsed_rows = session["parsed_rows"]
    valid_rows = [r for r in parsed_rows if not r.get("_skip")]

    # Merge region_mapping with auto-detected org matches
    combined_region_map: Dict[str, int] = dict(body.region_mapping)
    combined_owner_map: Dict[str, int] = dict(body.owner_mapping)

    inserted = 0
    updated = 0
    skipped = 0
    errors: list[dict] = []

    _VEHICLE_FIELDS = {
        "brand", "model", "color", "vin", "plate", "type", "state",
        "fuel_type", "fuel_norm_summer", "fuel_norm_winter", "next_to_km",
        "has_tracker", "akb_ok", "has_radio", "mirrors_ok",
        "has_keys", "has_first_aid_kit", "has_spare_wheel", "has_extinguisher",
        "registered_at", "insurance_until",
    }

    for row in valid_rows:
        plate = row.get("plate")
        row_n = row.get("_row_n", "?")

        try:
            # Resolve owner_org_id
            owner_text = row.get("owner_text") or ""
            owner_org_id: Optional[int] = (
                combined_owner_map.get(owner_text)
                or _match_org(owner_text, org_lookup)
                or body.default_owner_org_id
            )
            if owner_org_id is None:
                errors.append({"row": row_n, "plate": plate, "msg": "owner_org_id не определён — укажите default_owner_org_id"})
                continue

            # Resolve assigned_org_id
            assigned_text = row.get("assigned_text") or ""
            assigned_org_id: Optional[int] = (
                combined_region_map.get(assigned_text)
                or _match_org(assigned_text, org_lookup)
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
            from datetime import date as _date
            for dcol in ("registered_at", "insurance_until"):
                v = fields.get(dcol)
                if isinstance(v, str) and v:
                    try:
                        from datetime import datetime as _dt
                        fields[dcol] = _dt.strptime(v, "%Y-%m-%d").date()
                    except ValueError:
                        fields.pop(dcol, None)

            # Check existing
            existing_result = await db.execute(
                select(Vehicle).where(Vehicle.plate == plate)
            )
            existing: Optional[Vehicle] = existing_result.scalar_one_or_none()

            if existing is None:
                vehicle = Vehicle(**fields)
                db.add(vehicle)
                inserted += 1
            elif body.conflict_strategy == "update":
                for k, v in fields.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                skipped += 1

        except Exception as exc:
            logger.exception("vehicles_import commit row %s error", row_n)
            errors.append({"row": row_n, "plate": plate, "msg": str(exc)})

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
