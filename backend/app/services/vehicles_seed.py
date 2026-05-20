"""
vehicles_seed.py — Idempotent seed of vehicles from xlsx Голичкова.

Reads Доработки/реестр_транспорта_от_Голичкова_обновление_042026.xlsx (Лист2, 51 ТС).
Uses ON CONFLICT (plate) DO NOTHING — safe to run on every restart.

Plan 29-11, Decision D-09.
"""
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapping tables (per RESEARCH R-5)
# ---------------------------------------------------------------------------

TYPE_MAP = {
    'минивэн': 'minivan',
    'легковой': 'car_light',
    'легковая': 'car_light',
    'грузовой (фургон)': 'truck_van',
    'фургон': 'truck_van',
    'грузовой': 'truck_board',
    'бортовой': 'truck_board',
    'цистерна': 'truck_tank',
    'цельнометаллический': 'truck_metal',
    'автобус': 'bus',
    'спецтехника': 'special',
    'специальный': 'special',
    'квадроцикл': 'quadbike',
    'снегоход': 'snowmobile',
    'лодка': 'boat',
    'катер': 'boat',
    'лодочный мотор': 'boat_motor',
    'мотор лодочный': 'boat_motor',
    'прицеп': 'trailer',
}

STATE_MAP = {
    'рабочее': 'working',
    'исправно': 'working',
    'исправный': 'working',
    'неисправно': 'broken',
    'неисправен': 'broken',
    'в ремонте': 'in_repair',
    'требует ремонта': 'needs_repair',
    'утилизировано': 'utilized',
    'утилизирован': 'utilized',
}

FUEL_MAP = {
    'аи-92': 'AI-92', 'ai-92': 'AI-92',
    'аи-95': 'AI-95', 'ai-95': 'AI-95',
    'аи-98': 'AI-98', 'ai-98': 'AI-98',
    'дт': 'DT', 'дизель': 'DT', 'diesel': 'DT',
    'газ': 'GAS',
}


# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------

def _str(val) -> str:
    """Safe str(), strips whitespace, returns '' for None."""
    if val is None:
        return ''
    return str(val).strip()


def _bool_from_cell(val):
    """'да'/'есть'/'норм'/'+' → True; 'нет'/'отсутствует'/'-' → False; else None."""
    if val is None:
        return None
    s = _str(val).lower()
    if s in ('да', 'есть', 'исправно', 'норм', '+', 'true', 'yes', '1'):
        return True
    if s in ('нет', 'отсутствует', '-', 'false', 'no', '0', ''):
        return False
    return None


def _date_from_cell(val) -> date | None:
    """datetime/date value or DD.MM.YYYY string → date. None on failure."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = _str(val)
    if not s:
        return None
    # Try DD.MM.YYYY
    try:
        return datetime.strptime(s, '%d.%m.%Y').date()
    except ValueError:
        pass
    # Try ISO 8601 first 10 chars
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    log.debug(f"vehicles_seed: cannot parse date '{s}', skipping")
    return None


def _map_type(val: str) -> str:
    """Map raw «Тип ТС» cell value → VehicleType enum string."""
    if not val:
        return 'other'
    s = val.strip().lower()
    # Exact match first (longest key wins — iterate by key length desc)
    for k in sorted(TYPE_MAP, key=len, reverse=True):
        if k in s:
            return TYPE_MAP[k]
    log.warning(f"vehicles_seed: unknown vehicle type '{val}', mapping to 'other'")
    return 'other'


def _map_state(val: str) -> str:
    """Map raw «Состояние» cell value → VehicleState enum string."""
    if not val:
        return 'working'
    s = val.strip().lower()
    for k in sorted(STATE_MAP, key=len, reverse=True):
        if k in s:
            return STATE_MAP[k]
    return 'working'


def _map_fuel(val: str) -> str | None:
    """Map raw «Топливо» cell value → FuelType enum string or None."""
    if not val:
        return None
    s = val.strip().lower()
    for k, v in FUEL_MAP.items():
        if k in s:
            return v
    return None


def _split_brand_model(val: str) -> tuple[str, str]:
    """'Митсубиши Делика' → ('Митсубиши', 'Делика'). One word → (word, '')."""
    if not val:
        return ('', '')
    parts = val.strip().split(None, 1)
    return (parts[0], parts[1] if len(parts) > 1 else '')


# ---------------------------------------------------------------------------
# Owner org lookup
# ---------------------------------------------------------------------------

async def _lookup_owner_org_id(db: AsyncSession, raw_owner: str) -> int | None:
    """Try to resolve owner text → org id via case-insensitive name match.

    Returns org.id if found, None otherwise.
    Fallback (None) means caller should use default_owner_org_id=1 (ВСКС).
    """
    s = raw_owner.strip() if raw_owner else ''
    if not s:
        return None

    try:
        from app.models.organization import Organization
    except ImportError:
        try:
            from .app.models.organization import Organization
        except ImportError:
            # Absolute import path for container context
            import importlib
            mod = importlib.import_module('app.models.organization')
            Organization = mod.Organization

    # Exact ILIKE match
    result = await db.execute(
        select(Organization).where(Organization.name.ilike(s))
    )
    org = result.scalar_one_or_none()
    if org:
        return org.id

    # Substring match for "ВСКС"
    if 'вскс' in s.lower():
        result = await db.execute(
            select(Organization).where(Organization.name.ilike('%ВСКС%'))
        )
        org = result.scalar_one_or_none()
        if org:
            return org.id

    return None


# ---------------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------------

async def seed_vehicles_from_xlsx(
    db: AsyncSession,
    xlsx_path: str | None = None,
    *,
    force: bool = False,
) -> dict:
    """Idempotent seed from xlsx Голичкова.

    Args:
        db: AsyncSession — caller manages commit lifecycle.
        xlsx_path: Override default path. Defaults to Доработки/ at repo root.
        force: Unused (kept for API compatibility; ON CONFLICT already handles idempotency).

    Returns:
        {
          'total_in_xlsx': N,
          'inserted': N,
          'skipped_existing': N,
          'errors': [...],
          'reason': 'ok' | 'xlsx_not_found' | 'no_sheet',
        }
    """
    if xlsx_path is None:
        # In Docker container: /app/seed_data/vehicles_golichkov.xlsx
        # Local dev: backend/seed_data/vehicles_golichkov.xlsx
        backend_root = Path(__file__).parent.parent.parent  # /app
        xlsx_path = str(backend_root / 'seed_data' / 'vehicles_golichkov.xlsx')
        # Fallback на legacy путь Доработки/ для local dev backward compat
        if not os.path.exists(xlsx_path):
            repo_root = Path(__file__).parent.parent.parent.parent
            legacy_path = str(repo_root / 'Доработки' / 'реестр_транспорта_от_Голичкова_обновление_042026.xlsx')
            if os.path.exists(legacy_path):
                xlsx_path = legacy_path

    if not os.path.exists(xlsx_path):
        log.info(f"vehicles_seed: xlsx not found at '{xlsx_path}', seeding skipped (non-fatal)")
        return {
            'total_in_xlsx': 0,
            'inserted': 0,
            'skipped_existing': 0,
            'errors': [],
            'reason': 'xlsx_not_found',
        }

    try:
        import openpyxl
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    except Exception as exc:
        log.warning(f"vehicles_seed: failed to open xlsx: {exc}")
        return {
            'total_in_xlsx': 0,
            'inserted': 0,
            'skipped_existing': 0,
            'errors': [str(exc)],
            'reason': 'xlsx_open_error',
        }

    if 'Лист2' not in wb.sheetnames:
        log.warning(f"vehicles_seed: sheet 'Лист2' not found in xlsx (sheets: {wb.sheetnames})")
        return {
            'total_in_xlsx': 0,
            'inserted': 0,
            'skipped_existing': 0,
            'errors': ['sheet Лист2 not found'],
            'reason': 'no_sheet',
        }

    ws = wb['Лист2']
    rows = list(ws.iter_rows(values_only=True))[1:]  # skip header row

    DEFAULT_OWNER_ORG_ID = 1  # ВСКС (INN 7731178803, Gotcha 2026-04-23)

    inserted = 0
    skipped_existing = 0
    errors = []

    for idx, row in enumerate(rows, start=2):  # row number for error messages
        try:
            # ----------------------------------------------------------------
            # Required field: plate (col 4)
            # ----------------------------------------------------------------
            plate_raw = row[4] if len(row) > 4 else None
            if not plate_raw:
                continue  # skip empty rows silently
            plate = _str(plate_raw).upper()[:20]
            if not plate:
                continue

            # ----------------------------------------------------------------
            # VIN (col 3) — "отсутствует" or empty → None
            # ----------------------------------------------------------------
            vin_raw = _str(row[3] if len(row) > 3 else None)
            if vin_raw.lower() in ('отсутствует', 'нет', ''):
                vin = None
            else:
                vin = vin_raw.upper()[:17]

            # ----------------------------------------------------------------
            # Brand / Model (col 1)
            # ----------------------------------------------------------------
            brand, model = _split_brand_model(_str(row[1] if len(row) > 1 else None))
            brand = brand[:100]
            model = model[:100]

            # ----------------------------------------------------------------
            # Color (col 2)
            # ----------------------------------------------------------------
            color_raw = _str(row[2] if len(row) > 2 else None)
            color = color_raw[:50] if color_raw else None

            # ----------------------------------------------------------------
            # Owner / org (col 5)
            # ----------------------------------------------------------------
            owner_raw = _str(row[5] if len(row) > 5 else None)
            owner_org_id = await _lookup_owner_org_id(db, owner_raw)
            if owner_org_id is None:
                if owner_raw:
                    log.warning(
                        f"vehicles_seed row {idx}: owner '{owner_raw}' not found in orgs, "
                        f"fallback to ВСКС id={DEFAULT_OWNER_ORG_ID}"
                    )
                owner_org_id = DEFAULT_OWNER_ORG_ID

            # ----------------------------------------------------------------
            # Registered at (col 6)
            # ----------------------------------------------------------------
            registered_at = _date_from_cell(row[6] if len(row) > 6 else None)

            # ----------------------------------------------------------------
            # Assigned text (col 7 «У кого в эксплуатации»)
            # ----------------------------------------------------------------
            assigned_text = _str(row[7] if len(row) > 7 else None)[:100]

            # ----------------------------------------------------------------
            # Vehicle type (col 8)
            # ----------------------------------------------------------------
            v_type = _map_type(_str(row[8] if len(row) > 8 else None))

            # ----------------------------------------------------------------
            # Insurance until (col 9 «Страховка»)
            # ----------------------------------------------------------------
            insurance_until = _date_from_cell(row[9] if len(row) > 9 else None)

            # ----------------------------------------------------------------
            # State (col 10)
            # ----------------------------------------------------------------
            v_state = _map_state(_str(row[10] if len(row) > 10 else None))

            # ----------------------------------------------------------------
            # Boolean equipment flags (cols 11-14, 17-20)
            # ----------------------------------------------------------------
            has_tracker      = _bool_from_cell(row[11] if len(row) > 11 else None)
            akb_ok           = _bool_from_cell(row[12] if len(row) > 12 else None)
            has_radio        = _bool_from_cell(row[13] if len(row) > 13 else None)
            mirrors_ok       = _bool_from_cell(row[14] if len(row) > 14 else None)
            has_keys         = _bool_from_cell(row[17] if len(row) > 17 else None)
            has_first_aid_kit = _bool_from_cell(row[18] if len(row) > 18 else None)
            has_spare_wheel  = _bool_from_cell(row[19] if len(row) > 19 else None)
            has_extinguisher = _bool_from_cell(row[20] if len(row) > 20 else None)

            # ----------------------------------------------------------------
            # JSONB props (cols 15, 16, 21-23)
            # ----------------------------------------------------------------
            props = {
                'tires_type':         _str(row[15] if len(row) > 15 else None)[:200],
                'branding':           _str(row[16] if len(row) > 16 else None)[:200],
                'paint_condition':    _str(row[21] if len(row) > 21 else None)[:200],
                'defect_description': _str(row[22] if len(row) > 22 else None)[:500],
                'note':               _str(row[23] if len(row) > 23 else None)[:500],
            }

            # ----------------------------------------------------------------
            # INSERT ON CONFLICT (plate) DO NOTHING
            # ----------------------------------------------------------------
            try:
                async with db.begin_nested():
                    result = await db.execute(
                        text("""
                            INSERT INTO vehicles (
                                owner_org_id, assigned_org_id, assigned_text,
                                brand, model, color, vin, plate, registered_at,
                                type, state, insurance_until,
                                has_tracker, akb_ok, has_radio, mirrors_ok,
                                has_keys, has_first_aid_kit, has_spare_wheel, has_extinguisher,
                                props, created_at, updated_at
                            ) VALUES (
                                :owner_org_id, NULL, :assigned_text,
                                :brand, :model, :color, :vin, :plate, :registered_at,
                                :type, :state, :insurance_until,
                                :has_tracker, :akb_ok, :has_radio, :mirrors_ok,
                                :has_keys, :has_first_aid_kit, :has_spare_wheel, :has_extinguisher,
                                CAST(:props AS jsonb), NOW(), NOW()
                            )
                            ON CONFLICT (plate) DO NOTHING
                        """),
                        {
                            'owner_org_id':      owner_org_id,
                            'assigned_text':     assigned_text,
                            'brand':             brand,
                            'model':             model,
                            'color':             color,
                            'vin':               vin,
                            'plate':             plate,
                            'registered_at':     registered_at,
                            'type':              v_type,
                            'state':             v_state,
                            'insurance_until':   insurance_until,
                            'has_tracker':       has_tracker,
                            'akb_ok':            akb_ok,
                            'has_radio':         has_radio,
                            'mirrors_ok':        mirrors_ok,
                            'has_keys':          has_keys,
                            'has_first_aid_kit': has_first_aid_kit,
                            'has_spare_wheel':   has_spare_wheel,
                            'has_extinguisher':  has_extinguisher,
                            'props':             json.dumps(props, ensure_ascii=False),
                        },
                    )
                if result.rowcount and result.rowcount > 0:
                    inserted += 1
                else:
                    skipped_existing += 1
            except Exception as sql_exc:
                err_msg = f"row {idx} (plate={plate_raw!r}): SQL: {sql_exc}"
                log.warning(f"vehicles_seed: SQL error row {idx} — savepoint rolled back: {sql_exc}")
                errors.append(err_msg)

        except Exception as row_exc:
            err_msg = f"row {idx} (plate={plate_raw!r}): parse: {row_exc}"
            log.warning(f"vehicles_seed: skipping malformed row — {err_msg}")
            errors.append(err_msg)
            continue

    await db.commit()

    total = len(rows)
    log.info(
        f"vehicles_seed: total_in_xlsx={total}, inserted={inserted}, "
        f"skipped_existing={skipped_existing}, errors={len(errors)}"
    )
    return {
        'total_in_xlsx': total,
        'inserted': inserted,
        'skipped_existing': skipped_existing,
        'errors': errors,
        'reason': 'ok',
    }
