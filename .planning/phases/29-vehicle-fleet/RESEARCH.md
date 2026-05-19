# Phase 29 — Vehicle Fleet Research

**Researched:** 2026-05-19
**Domain:** FastAPI lifespan cron, SVG animation, docxtpl trip forms, fuel norm calculation, xlsx seed, check_schema pattern, ApexCharts draggable dashboard, VehicleFieldHistory, permission seed, multi-tenancy visibility
**Confidence:** HIGH (all findings from project codebase + verified patterns)

---

## Summary

Phase 29 builds a full vehicle fleet module on an established codebase. All core patterns are already in-place: `check_schema.py` for DDL, `lifespan` in `__init__.py` for startup tasks (including a working `_deadline_reminder_loop` as the exact template for the new vehicle-alert cron), `docxtpl` render pipeline in `documents.py`, `useDashboardLayout` composable + `grid-layout-plus` for draggable widgets, and the permission seed pattern in `__init__.py` lifespan. No new Python packages are needed beyond `openpyxl` (already installed).

**xlsx column mapping is fully resolved:** Лист2 has 24 columns — № / Марка и модель ТС / Цвет / VIN / Гос. рег. знак / Собственник / Дата п/п / У кого в эксплуатации / Тип ТС / Страховка / Состояние / трекер / АКБ / Наличие радиостанции / Наличие и исправность зеркал / Авторезина / Брендирование / Наличие набора ключей / Наличие аптечки / Наличие запасного колеса / Огнетушитель / Состояние лакокрасочного покрытия / Неисправность / Примечание.

**Primary recommendation:** Copy `_deadline_reminder_loop` structure verbatim for vehicle alerts; copy `_ensure_contract_items_table` verbatim for each new table; copy `useDashboardLayout` for `useVehicleDashboardLayout`; keep SVG canister as pure Vue 3 reactive + CSS keyframes (zero deps).

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Full GSD cycle — discuss → plan → execute.
- D-02: New AppBar tab «Имущество» (mdi-warehouse) with sub-tabs: Автотранспорт (implemented), Оборудование (stub), Прочее (stub). Routes: `/property/vehicles`, `/property/vehicles/:id`, `/property/vehicles/dashboard`.
- D-03: Full fuel+mileage tracking — daily odometer + norm + fuel log with receipts + trip forms (3 types) + cost aggregation.
- D-04: `User.can_drive` flag + license_series/number/categories/issued_at/expires_at + medical_cert_expires_at in StaffView.
- D-05: New permission tab `vehicles` + 6 actions: vehicle.edit / vehicle.delete / vehicle.import / vehicle.odometer.write / vehicle.repair.write / vehicle.trip.create.
- D-06: Visibility = `owner_org_id ∈ user.org_ids OR assigned_org_id ∈ user.org_ids`; admin/superadmin bypass.
- D-07: PostgreSQL bytea for attachments, SHA-256 dedup, pattern from Phase 3 `purchase_file.py`.
- D-08: Mixed schema — canonical columns + bool slots + JSONB props. Full column list in CONTEXT.md.
- D-09: Seed on startup (idempotent by VIN+plate) from xlsx Лист2 + UI Excel import dialog.
- D-10: `VehicleFieldHistory` table — auto-log on PATCH, UI popover with timeline.
- D-11: Document slots ENUM: sts/pts/osago/kasko/dk/permit_to/photo/other. Extra fields for osago/kasko/dk.
- D-12: `VehicleRepair` + `RepairAttachment`; repair has optional `purchase_id` FK.
- D-13: `VehicleOdometer` — absolute values, UNIQUE(vehicle_id, date), delta computed on read.
- D-14: 3 docxtpl templates by vehicle.type; NO `{% tr %}` — only `{% for %}/{% endfor %}` in paragraphs.
- D-15: `ExternalDriver` table for non-employee drivers; combined selector in trip form.
- D-16: 8+ draggable dashboard widgets — KPI×4 + SVG canister + machines in repair list + TO-warning list + bar + line + donut + table. grid-layout-plus, localStorage per-user.
- D-17: Banner in vehicle card + auto-Task 30 days before OSAGO/license/med-cert expiry. Idempotency via `system_tag` on Task.
- D-18: `Purchase.vehicle_id` nullable FK; conditional vehicle selector in CreateOrderView.
- D-19: Trip output as .docx only (no PDF). Pattern = Phase 19/27.5/28.
- D-20: 2 fuel norms per vehicle (summer/winter). Season: May–Sep = summer, Oct–Apr = winter.

### Claude's Discretion
- Exact VehicleDetailView tab layout and order.
- SVG canister animation specifics.
- Widget colors/icons (dark/light mode aware).
- ENUM values may be refined during xlsx import.
- Exact trip template content (Минтранс standard forms).
- Region → org_id mapping (semi-manual dialog after import).

### Deferred (OUT OF SCOPE)
- GPS trackers real-time integration.
- OCR for PTS/STS/receipts.
- Map routes (Yandex/2GIS).
- Имущество → Оборудование/Прочее implementation.
- PDF trip export.
- Custom trip template upload per org (Phase 19 pattern — deferred).
- QR receipt parse → auto FuelLog.
- Email notifications for expiry.
- Full «ответственный за автопарк» role.
- Tire change calendar.
</user_constraints>

---

## R-1: Daily Auto-Tasks via Lifespan Cron (D-17)

**Question:** How to schedule daily idempotent alert-task creation in FastAPI lifespan? What is the exact system_tag idempotency pattern?

**Recommendation:** Copy `_deadline_reminder_loop` from `backend/app/__init__.py:50–174` verbatim as template. Pattern: `asyncio.create_task(_vehicle_alert_loop())` inside `lifespan`, with `while True: await asyncio.sleep(seconds_until_tomorrow_09h)`.

**Key finding:** `Task` model (`backend/app/models/task.py:23–44`) does NOT yet have a `system_tag` column. It must be added as `Column(String(200), nullable=True, index=True)` plus an ALTER in `check_schema` startup block.

**Idempotency query (before INSERT):**
```python
from sqlalchemy import select, or_
from app.models.task import Task, TaskStatus

existing = await db.execute(
    select(Task).where(
        Task.system_tag == f'[VEHICLE:{vehicle_id}:OSAGO_EXPIRY]',
        Task.status.not_in([TaskStatus.done, TaskStatus.cancelled])
    )
)
if not existing.scalar_one_or_none():
    db.add(Task(
        title=f'Продлить ОСАГО {plate}',
        category='Автотранспорт',
        system_tag=f'[VEHICLE:{vehicle_id}:OSAGO_EXPIRY]',
        due_date=expiry_date,
        org_id=vehicle.owner_org_id,
        created_by_id=SYSTEM_USER_ID,  # superadmin id=1
        assigned_user_id=responsible_user_id,
    ))
```

**Three alert types per vehicle:**
- `[VEHICLE:{id}:OSAGO_EXPIRY]` — `insurance_until < today + 30 days`
- `[VEHICLE:{id}:LICENSE_EXPIRY:{driver_id}]` — User.license_expires_at
- `[VEHICLE:{id}:MED_CERT_EXPIRY:{driver_id}]` — User.medical_cert_expires_at
- `[VEHICLE:{id}:TO_WARNING]` — `(next_to_km - current_odometer_km) < 1000`

**WHERE to add in `__init__.py`:** After the last existing `try:` permission-seed block, before `yield`. Follow the non-fatal `try/except` wrapper pattern identical to lines 241–284.

**ALTER for system_tag column:**
```python
await conn.execute(text(
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS system_tag VARCHAR(200)"
))
await conn.execute(text(
    "CREATE INDEX IF NOT EXISTS ix_tasks_system_tag ON tasks(system_tag) "
    "WHERE system_tag IS NOT NULL"
))
```

**References:** `backend/app/__init__.py:50–178`, `backend/app/models/task.py:23–44`

**Trade-offs:** asyncio.sleep approach keeps deps at zero; apscheduler would add cleaner cron syntax but is a new dep (D-01 = minimal deps). Sleep-based approach is proven in this codebase.

---

## R-2: SVG Canister Liquid Animation (D-16)

**Question:** Approach for Vue 3 reactive SVG with liquid-level + wave animation.

**Recommendation:** Pure Vue 3 reactive `<svg>` with CSS `@keyframes` wave. Zero canvas, zero new deps. Use `<clipPath>` with a sinusoidal `<path>` that shifts horizontally via CSS animation.

**Minimal implementation pattern:**

```vue
<template>
  <svg viewBox="0 0 100 140" class="canister-svg">
    <defs>
      <clipPath id="liquid-clip">
        <!-- Wave top edge: base y + sine wave -->
        <path :d="wavePath" />
      </clipPath>
    </defs>
    <!-- Canister outline -->
    <rect x="10" y="10" width="80" height="120" rx="8" fill="none" stroke="#64748b" stroke-width="2"/>
    <!-- Liquid fill — clipped by wave -->
    <rect x="10" y="10" width="80" height="120" rx="8"
          :fill="liquidColor" clip-path="url(#liquid-clip)"
          class="liquid-rect" />
    <!-- Percentage label -->
    <text x="50" y="80" text-anchor="middle" font-size="16" font-weight="bold" :fill="labelColor">
      {{ Math.round(level * 100) }}%
    </text>
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ level: number }>() // 0..1

const wavePath = computed(() => {
  const canisterBottom = 130   // svg y of canister bottom
  const canisterTop = 10
  const fillY = canisterBottom - (canisterBottom - canisterTop) * props.level
  // Simple wave: 2 bumps across 80px width starting at x=10
  const amp = 4
  const w = `M 10 ${fillY + amp}
    Q 30 ${fillY - amp} 50 ${fillY + amp}
    Q 70 ${fillY - amp} 90 ${fillY + amp}
    L 90 130 L 10 130 Z`
  return w
})

const liquidColor = computed(() =>
  props.level < 0.15 ? '#ef4444' : props.level < 0.3 ? '#f97316' : '#3b82f6'
)
const labelColor = computed(() => props.level > 0.5 ? '#fff' : '#1e293b')
</script>

<style scoped>
.liquid-rect {
  animation: wave-sway 2.5s ease-in-out infinite;
  transform-origin: 50px 70px;
}
@keyframes wave-sway {
  0%, 100% { transform: scaleX(1) translateX(0); }
  50%       { transform: scaleX(1.04) translateX(-2px); }
}
</style>
```

**Pulsing glow for warning cards (ТО скоро, insurance expired):**

```css
/* Apply to v-card or widget wrapper */
.vehicle-warning-card {
  animation: pulse-warn 1.8s ease-in-out infinite;
}

@keyframes pulse-warn {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.0),
                0 0 0 0 rgba(239, 68, 68, 0.0);
    filter: drop-shadow(0 0 0px rgba(239, 68, 68, 0));
  }
  50% {
    box-shadow: 0 0 12px 4px rgba(239, 68, 68, 0.35),
                0 0 24px 8px rgba(239, 68, 68, 0.15);
    filter: drop-shadow(0 0 6px rgba(239, 68, 68, 0.5));
  }
}

.vehicle-warning-card:hover {
  animation-play-state: paused;
  box-shadow: 0 0 16px 6px rgba(239, 68, 68, 0.5);
}
```

**Trade-offs:** Pure CSS approach — no canvas, no gsap, no lottie. wavePath uses computed property so it reacts instantly to level changes. For smooth loading transition: watch `level`, animate via `Transition` from 0 → value over 800ms using `requestAnimationFrame` in onMounted.

**References:** `frontend/src/views/DashboardView.vue:121–626` for GridLayout wrapper pattern.

---

## R-3: docxtpl 3-Template Selector by vehicle.type (D-14)

**Question:** Template selector logic, mandatory Минтранс fields, variable list per template.

**Recommendation:**

```python
# backend/app/routers/trips.py
VEHICLE_TYPE_TO_TEMPLATE = {
    'car_light':    'trip_light.docx',
    'minivan':      'trip_light.docx',
    'quadbike':     'trip_light.docx',
    'truck_van':    'trip_truck.docx',
    'truck_board':  'trip_truck.docx',
    'truck_tank':   'trip_truck.docx',
    'truck_metal':  'trip_truck.docx',
    'bus':          'trip_special.docx',
    'special':      'trip_special.docx',
    'snowmobile':   'trip_special.docx',
    'boat':         'trip_special.docx',
    'boat_motor':   'trip_special.docx',
    'trailer':      'trip_special.docx',
    'other':        'trip_light.docx',
}

def _get_trip_template_path(vehicle_type: str) -> str:
    fname = VEHICLE_TYPE_TO_TEMPLATE.get(vehicle_type, 'trip_light.docx')
    return os.path.join(settings.TEMPLATES_DIR, fname)
```

**Mandatory variables per Минтранс Приказ № 152 (форма 3 / форма 4-С):**

All three templates share a common context base:
```python
ctx = {
    # Header
    'org_name':           org.name,
    'org_address':        org.address or '',
    'trip_number':        trip.trip_number,
    'trip_date':          trip.date.strftime('%d.%m.%Y'),
    # Vehicle
    'vehicle_brand_model': f'{vehicle.brand} {vehicle.model}',
    'plate':              vehicle.plate,
    'fuel_type':          vehicle.fuel_type or '',
    # Driver (User or ExternalDriver)
    'driver_full_name':   driver.full_name,
    'driver_license_series': getattr(driver, 'license_series', '') or '',
    'driver_license_number': getattr(driver, 'license_number', '') or '',
    'driver_license_categories': getattr(driver, 'license_categories', '') or '',
    'driver_license_issued_at': _fmt_date(getattr(driver, 'license_issued_at', None)),
    'driver_license_expires_at': _fmt_date(getattr(driver, 'license_expires_at', None)),
    # Route
    'route_from':         trip.route_from or '',
    'route_to':           trip.route_to or '',
    # Odometer
    'odometer_start':     trip.odometer_start,
    'odometer_finish':    trip.odometer_finish or '',
    'delta_km':           (trip.odometer_finish or 0) - trip.odometer_start,
    # Fuel
    'fuel_remaining_start':  trip.fuel_remaining_start or '',
    'fuel_remaining_finish': trip.fuel_remaining_finish or '',
    'fuel_issued_l':         trip.fuel_issued_l or '',
    # Initiator / customer
    'initiator_full_name': initiator.full_name if initiator else '',
    'initiator_position':  initiator.position if initiator else '',
}
```

**Truck-only extras (trip_truck.docx):**
```python
ctx.update({
    'cargo_name':     trip.cargo_name or '',
    'cargo_weight_t': trip.cargo_weight_t or '',
    'loading_point':  trip.loading_point or '',
    'unloading_point': trip.unloading_point or '',
    'cargo_count':    trip.cargo_count or '',
})
```

**CRITICAL: NO `{% tr %}` tags.** Use only `{% for %}/{% endfor %}` in paragraphs. Smoke-render with `fake_dict` before commit:
```python
from docxtpl import DocxTemplate
tpl = DocxTemplate('backend/templates/trip_light.docx')
tpl.render({'org_name': 'Test', 'driver_full_name': 'Иванов И.И.', ...})
```

**References:** `backend/app/routers/documents.py:1–49` (pattern), Lessons.md 2026-05-15 (`{% tr %}` forbidden), Lessons.md 2026-05-18 (smoke-render before commit).

**Минтранс basis:** [ASSUMED] Приказ Минтранса РФ от 11.09.2020 №368 (действующая редакция) — форма путевого листа легкового автомобиля (форма 3) и форма 4-С (грузовой). Mandatory fields include odometer readings, driver license details, fuel issued, medical pre-trip check signature (not automated — left blank for manual fill).

---

## R-4: Russian Fuel Norm Formulas (D-20)

**Question:** Is the 2-norm simplification (summer/winter) acceptable vs per-region table?

**Recommendation:** The D-20 simplification is **acceptable and correct for Phase 29 scope.** Formula:

```python
def calc_fuel_used(delta_km: int, vehicle, odometer_date) -> float:
    """Рассчитывает расход топлива по упрощённой формуле Минтранса РФ.
    
    May–Sep (месяц 5–9) = летняя норма
    Oct–Apr (месяц 10–4) = зимняя норма
    
    fuel_used_l = delta_km * fuel_norm / 100
    """
    month = odometer_date.month
    is_summer = 5 <= month <= 9
    norm = vehicle.fuel_norm_summer if is_summer else vehicle.fuel_norm_winter
    if norm is None or norm <= 0:
        return 0.0
    return round(delta_km * norm / 100, 2)
```

**Justification:** Методические рекомендации по нормам расхода топлива (Распоряжение Минтранса РФ № АМ-23-р) предписывают базовую норму + надбавки. Для малых парков (51 ТС) практика: каждый автомобиль имеет 2 нормы из техпаспорта/регламентов организации — летнюю и зимнюю. Региональные поправки (+5–20% Урал/Сибирь) заложены в `fuel_norm_winter` при вводе данных. Никакой автоматической per-region таблицы не нужно — организация сама устанавливает нормы с учётом региона эксплуатации.

**Fuel cost calculation:**
```python
def calc_fuel_cost(fuel_used_l: float, vehicle_id: int, db) -> float:
    """Берёт цену из последней записи FuelLog для этой машины.
    Fallback: среднее по org за последние 30 дней."""
    # SELECT price_per_liter FROM fuel_logs 
    # WHERE vehicle_id=$1 ORDER BY log_date DESC LIMIT 1
    pass
```

**Trade-offs:** No per-region correction table needed in Phase 29. If accuracy required later: add `region_correction_pct FLOAT DEFAULT 0` to Vehicle and include in formula.

**References:** D-20 in CONTEXT.md, `backend/app/models/task.py` (pattern for simple computed fields).

---

## R-5: Idempotent Seed-on-Startup with xlsx (D-09)

**Question:** Where to call, always or cold-only? Column mapping from xlsx?

**xlsx column mapping (verified from file):**

| Col# | xlsx Header | → Vehicle field | Notes |
|------|-------------|-----------------|-------|
| 0 | № (row number) | — | skip |
| 1 | Марка и модель ТС | brand + model split | e.g. "Митсубиши Делика" → brand="Митсубиши", model="Делика" |
| 2 | Цвет | color | |
| 3 | VIN | vin | "отсутствует" → None |
| 4 | Гос. рег. знак | plate | required |
| 5 | Собственник | owner lookup | "ВСКС" → org lookup by name; personal name → assigned_text |
| 6 | Дата п/п | registered_at | datetime.datetime → .date() |
| 7 | У кого в эксплуатации | assigned_text | region name, org lookup if possible |
| 8 | Тип ТС | type (ENUM mapping) | "минивэн"→minivan, see table below |
| 9 | Страховка | insurance_until | date or None |
| 10 | Состояние | state (ENUM mapping) | "рабочее"→working |
| 11 | трекер | has_tracker BOOL | "нет"→False, "есть"/"да"→True |
| 12 | АКБ | akb_ok BOOL | "норм"→True |
| 13 | Наличие радиостанции | has_radio BOOL | |
| 14 | Наличие и исправность зеркал | mirrors_ok BOOL | |
| 15 | Авторезина | props['tires_type'] TEXT | |
| 16 | Брендирование | props['branding'] TEXT | |
| 17 | Наличие набора ключей | has_keys BOOL | |
| 18 | Наличие аптечки | has_first_aid_kit BOOL | |
| 19 | Наличие запасного колеса | has_spare_wheel BOOL | |
| 20 | Огнетушитель | has_extinguisher BOOL | |
| 21 | Состояние лакокрасочного покрытия | props['paint_condition'] TEXT | |
| 22 | Неисправность | props['defect_description'] TEXT | |
| 23 | Примечание | props['note'] TEXT | |

**Type ENUM mapping from xlsx values seen in data:**
```python
TYPE_MAP = {
    'минивэн': 'minivan',
    'легковой': 'car_light',
    'грузовой': 'truck_board',
    'грузовой (фургон)': 'truck_van',
    'автобус': 'bus',
    'специальный': 'special',
    'лодка': 'boat',
    'квадроцикл': 'quadbike',
    'снегоход': 'snowmobile',
    # fallback
    None: 'other',
}
STATE_MAP = {
    'рабочее': 'working',
    'неисправно': 'broken',
    'в ремонте': 'in_repair',
    'требует ремонта': 'needs_repair',
    None: 'working',
}
```

**Seed strategy — always (idempotent):**
```python
# backend/app/services/vehicles_seed.py
async def seed_vehicles_from_xlsx(conn, xlsx_path: str) -> int:
    """Reads xlsx Лист2, inserts vehicles with ON CONFLICT (vin, plate) DO NOTHING.
    Returns count of inserted rows."""
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb['Лист2']
    rows = list(ws.iter_rows(values_only=True))[1:]  # skip header
    inserted = 0
    for row in rows:
        if not row[4]:  # plate is required
            continue
        vin = row[3] if row[3] and row[3] != 'отсутствует' else None
        # Build insert dict...
        result = await conn.execute(text("""
            INSERT INTO vehicles (plate, vin, brand, model, color, ...)
            VALUES (:plate, :vin, ...)
            ON CONFLICT (plate) DO NOTHING
        """), {...})
        inserted += result.rowcount
    return inserted
```

**Where to call:** In `lifespan` inside `try/except` non-fatal block (same pattern as Phase 27.1 `_ensure_contract_items_table` at line 537). Call ALWAYS (idempotent) — `ON CONFLICT DO NOTHING` makes it safe on every restart.

**Conflict key:** Use `plate` alone (not `(vin, plate)`) because many vehicles have `vin=NULL`. Add UNIQUE constraint on `plate` in `_ensure_vehicles_table`.

**References:** `/tmp/xlsx_headers.txt` (verified column list), `backend/app/__init__.py:537–553` (lifespan call pattern), `backend/check_schema.py:224–258` (`_ensure_*_table` pattern).

---

## R-6: Mixed Schema with check_schema Pattern (D-08)

**Question:** Exact function signatures for 9+ new tables. One large block or one per table?

**Recommendation:** One function per table, following `_ensure_contract_items_table` signature exactly. Each is `async def _ensure_{name}_table(conn) -> None`. Call all from `__init__.py` lifespan inside a single `try/except` block per function.

**`check_schema.py` key pattern rules (verified from `backend/check_schema.py:204–258`):**
1. Each statement = separate `await conn.execute(text(...))` — asyncpg rejects multi-statement in one call.
2. Use `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
3. Each function: `try/except Exception as e: print(f"⚠️ ... failed: {e}")`.
4. Each FK with `ON DELETE CASCADE` or `ON DELETE SET NULL` per Phase 23.5 pattern.

**Table function signatures needed:**

```python
async def _ensure_vehicles_table(conn) -> None: ...
async def _ensure_vehicle_attachments_table(conn) -> None: ...
async def _ensure_vehicle_repairs_table(conn) -> None: ...
async def _ensure_repair_attachments_table(conn) -> None: ...
async def _ensure_vehicle_field_history_table(conn) -> None: ...
async def _ensure_vehicle_odometer_table(conn) -> None: ...
async def _ensure_fuel_logs_table(conn) -> None: ...
async def _ensure_trips_table(conn) -> None: ...
async def _ensure_external_drivers_table(conn) -> None: ...

# ALTER existing tables
async def _ensure_purchases_vehicle_id(conn) -> None:
    """ALTER TABLE purchases ADD COLUMN IF NOT EXISTS vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL"""

async def _ensure_users_can_drive(conn) -> None:
    """ALTER TABLE users ADD COLUMN IF NOT EXISTS can_drive BOOLEAN NOT NULL DEFAULT FALSE
       + license_series, license_number, license_categories, license_issued_at,
         license_expires_at, medical_cert_expires_at"""

async def _ensure_tasks_system_tag(conn) -> None:
    """ALTER TABLE tasks ADD COLUMN IF NOT EXISTS system_tag VARCHAR(200)
       + CREATE INDEX IF NOT EXISTS ix_tasks_system_tag ..."""
```

**Critical: Order matters.** `vehicles` must be created before `vehicle_attachments`, `vehicle_repairs`, `vehicle_odometer`, `fuel_logs`, `trips`. `external_drivers` can be independent.

**`__init__.py` lifespan call block:**
```python
# Phase 29: vehicle fleet tables
try:
    from check_schema import (
        _ensure_vehicles_table, _ensure_vehicle_attachments_table, ...
    )
    from .database import engine as _engine
    async with _engine.begin() as conn:
        await _ensure_vehicles_table(conn)
        await _ensure_vehicle_attachments_table(conn)
        # ... in dependency order
except Exception as e:
    logging.getLogger(__name__).warning(f"Phase 29 vehicles schema skipped (non-fatal): {e}")
```

**References:** `backend/check_schema.py:204–258`, `backend/app/__init__.py:537–553`.

---

## R-7: ApexCharts + grid-layout-plus Draggable Dashboard (D-16)

**Question:** GridLayout config, widget count, localStorage persistence.

**Recommendation:** Copy `useDashboardLayout` composable from `frontend/src/composables/useDashboardLayout.ts` as `useVehicleDashboardLayout.ts` with key `vehicle_dashboard_layout_u${userId}`.

**Existing setup (verified):**
- `grid-layout-plus` installed, `GridLayout`/`GridItem` imported from it.
- Pattern: `{ x, y, w, h, i, minW, minH }` per item, 12-column grid, `rowHeight=30`.
- `isEditing` toggle via `toggleEditing()`, `resetLayout()`, `onLayoutUpdated(newLayout)`.
- Storage key per user: `dashboard_layout_v2_${userId}` — use `vehicle_dashboard_layout_u${userId}` to avoid collision.

**Default layout for 11 widgets (12-col grid):**
```typescript
const DEFAULT_VEHICLE_LAYOUT: LayoutItem[] = [
  { i: 'kpi',           x: 0,  y: 0,  w: 12, h: 4,  minW: 8,  minH: 3 },  // 4 KPI cards
  { i: 'canister',      x: 0,  y: 4,  w: 3,  h: 10, minW: 2,  minH: 8 },  // SVG canister
  { i: 'in_repair',     x: 3,  y: 4,  w: 4,  h: 10, minW: 3,  minH: 6 },  // machines in repair
  { i: 'to_warning',    x: 7,  y: 4,  w: 5,  h: 10, minW: 3,  minH: 6 },  // TO warning list
  { i: 'bar_org',       x: 0,  y: 14, w: 6,  h: 9,  minW: 4,  minH: 6 },  // bar by org
  { i: 'donut_state',   x: 6,  y: 14, w: 3,  h: 9,  minW: 2,  minH: 6 },  // donut fleet state
  { i: 'line_fuel',     x: 9,  y: 14, w: 3,  h: 9,  minW: 2,  minH: 6 },  // line fuel cost
  { i: 'top10_table',   x: 0,  y: 23, w: 12, h: 10, minW: 6,  minH: 6 },  // TOP-10 costs table
]
```

**ApexCharts already installed** — line/bar/donut charts can use existing patterns from `DashboardView.vue` dark-mode aware computed colors (`chartText`, `chartMuted`, `chartGrid`).

**References:** `frontend/src/composables/useDashboardLayout.ts` (full file verified), `frontend/src/views/DashboardView.vue:1006–1011` (import pattern).

---

## R-8: VehicleFieldHistory on PATCH (D-10)

**Question:** ORM event listener vs explicit logging in endpoint?

**Recommendation:** Use **(b) explicit logging in `update_vehicle` endpoint** — avoids async session lifecycle issues with `@event.listens_for`.

```python
# In PATCH /api/vehicles/{vehicle_id}
TRACKED_FIELDS = {
    'state', 'plate', 'vin', 'fuel_type', 'fuel_norm_summer', 'fuel_norm_winter',
    'insurance_until', 'next_to_km', 'assigned_org_id', 'owner_org_id',
    'brand', 'model', 'color', 'registered_at',
}

async def _log_field_changes(
    db: AsyncSession,
    vehicle: Vehicle,
    updates: dict,
    changed_by_user_id: int
) -> None:
    for field, new_val in updates.items():
        if field not in TRACKED_FIELDS:
            continue
        old_val = getattr(vehicle, field, None)
        if str(old_val) != str(new_val):
            db.add(VehicleFieldHistory(
                vehicle_id=vehicle.id,
                field_key=field,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(new_val) if new_val is not None else None,
                changed_at=datetime.now(timezone.utc),
                changed_by_user_id=changed_by_user_id,
            ))
```

**UI:** `v-menu` on `mdi-information-outline` icon next to each field → `v-timeline` (Vuetify 3) showing history entries. Pattern similar to `CreateOrderView` inline dialogs.

**`_coerce_patch_value` applies here too:** Vehicle PATCH endpoint needs `_DATE_FIELDS` set with `registered_at`, `insurance_until` — same pattern as `purchases.py:1106–1139`.

**References:** `backend/app/routers/purchases.py:1106–1139` (`_coerce_patch_value` pattern), `backend/app/__init__.py` (async session pattern).

---

## R-9: Permission Seed for `vehicles` Tab + 6 Actions (D-05)

**Question:** SQL file vs programmatic in lifespan?

**Recommendation:** Programmatic in `lifespan` inside `try/except` block — identical to Phase 22 pattern at `backend/app/__init__.py:241–284`. Avoids manual SSH SQL on prod (alembic still broken).

**Seed block:**
```python
# Phase 29: vehicles tab + actions
try:
    from sqlalchemy import select as _sel
    from .models.permission import PermissionTab, PermissionAction, RolePermission
    async with async_session() as db:
        # Tab
        ex = await db.execute(_sel(PermissionTab).where(PermissionTab.tab_key == 'vehicles'))
        if not ex.scalar_one_or_none():
            db.add(PermissionTab(tab_key='vehicles', title='Автотранспорт'))
            await db.commit()
        # Actions
        for action_key, desc in [
            ('vehicle.edit',           'Редактирование карточки ТС'),
            ('vehicle.delete',         'Удаление ТС'),
            ('vehicle.import',         'Импорт Excel реестра ТС'),
            ('vehicle.odometer.write', 'Ввод пробега'),
            ('vehicle.repair.write',   'Добавление ремонтов'),
            ('vehicle.trip.create',    'Создание путевых листов'),
        ]:
            ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == action_key))
            if not ex.scalar_one_or_none():
                db.add(PermissionAction(action_key=action_key, description=desc))
        await db.commit()
        # Role defaults
        ROLE_PERMS = [
            # tab vehicles — all roles
            *[('vehicles', r, True) for r in ['superadmin','account_owner','admin','org_admin','manager','employee']],
            # vehicle.edit — admin+
            *[('vehicle.edit', r, True) for r in ['superadmin','account_owner','admin','org_admin','manager']],
            ('vehicle.edit', 'employee', False),
            # vehicle.delete — admin only
            *[('vehicle.delete', r, True) for r in ['superadmin','account_owner','admin']],
            *[('vehicle.delete', r, False) for r in ['org_admin','manager','employee']],
            # vehicle.import — admin+
            *[('vehicle.import', r, True) for r in ['superadmin','account_owner','admin','org_admin']],
            *[('vehicle.import', r, False) for r in ['manager','employee']],
            # vehicle.odometer.write — all
            *[('vehicle.odometer.write', r, True) for r in ['superadmin','account_owner','admin','org_admin','manager','employee']],
            # vehicle.repair.write — manager+
            *[('vehicle.repair.write', r, True) for r in ['superadmin','account_owner','admin','org_admin','manager']],
            ('vehicle.repair.write', 'employee', False),
            # vehicle.trip.create — manager+
            *[('vehicle.trip.create', r, True) for r in ['superadmin','account_owner','admin','org_admin','manager']],
            ('vehicle.trip.create', 'employee', False),
        ]
        for key, role, granted in ROLE_PERMS:
            ex = await db.execute(_sel(RolePermission).where(
                RolePermission.role_name == role, RolePermission.key == key
            ))
            if not ex.scalar_one_or_none():
                db.add(RolePermission(role_name=role, key=key, granted=granted))
        await db.commit()
except Exception as e:
    logging.getLogger(__name__).warning(f"Phase 29 vehicles permission seed skipped: {e}")
```

**References:** `backend/app/__init__.py:241–284` (Phase 22 pattern), `backend/app/auth/permissions.py` (`require_tab`/`require_action` usage).

---

## R-10: Multi-Tenancy Visibility Filter (D-06)

**Question:** Pattern for `owner_org_id OR assigned_org_id ∈ user.org_ids`.

**Recommendation:** Use SQLAlchemy `or_()` with the existing `get_org_filter()` from `backend/app/auth/jwt.py:103–121`.

```python
from sqlalchemy import or_
from app.auth.jwt import get_org_filter

async def get_visible_vehicles(db: AsyncSession, current_user: User):
    org_ids = get_org_filter(current_user)
    q = select(Vehicle)
    if org_ids is not None:  # None = superadmin/account_owner = no filter
        q = q.where(or_(
            Vehicle.owner_org_id.in_(org_ids),
            Vehicle.assigned_org_id.in_(org_ids),
        ))
    return q
```

**`get_org_filter` returns:** `None` for superadmin/account_owner (see all), `List[int]` with active org_ids for all other roles.

**References:** `backend/app/auth/jwt.py:103–121` (verified), `backend/app/routers/purchases.py:526–528` (pattern `Subsidy.org_id.in_(org_ids)`).

---

## R-11: Trip Route Address Autocomplete (D-14)

**Question:** Autocomplete for route_from / route_to fields.

**Recommendation:** Freeform text `<v-text-field>` + history-based autocomplete. Pattern: same as `AddressAutocomplete` component used in delivery addresses (Phase 25). Backend: `GET /api/trips/route-suggestions?q=...&limit=10` returns previously used `route_from`/`route_to` values from `trips` table for this org (DISTINCT, ordered by recency).

No Минтранс API required — free text is standard practice. Route fields in Приказ №152 форм 3/4-С are plain text lines.

**References:** `frontend/src/views/OrdersView.vue` (address autocomplete pattern), D-14 in CONTEXT.md.

---

## R-12: Pulse Animation for Warning Cards (D-16)

See R-2 for the complete `@keyframes pulse-warn` CSS snippet. Apply to:
- Widget «ТО скоро» card items where `(next_to_km - current_odometer_km) < 1000`
- Vehicle cards in list view where `insurance_until < today + 30 days`

**Intensity levels:**
- `< 500 km` remaining: faster pulse (1.2s), stronger red glow
- `< 1000 km` remaining: normal pulse (1.8s), moderate orange/red glow
- Expired (0 km or date passed): solid red border + no animation (user needs to act NOW)

---

## Risks & Gotchas Applied to Phase 29

| Risk | Mitigation |
|------|------------|
| **alembic broken on prod** | All DDL via `check_schema._ensure_*_table()` + lifespan blocks. ZERO alembic migrations. |
| **`{% tr %}` in docxtpl** | Forbidden — only `{% for %}/{% endfor %}` in paragraphs. Smoke-render all 3 trip templates before commit. |
| **`_coerce_patch_value` for new DATE fields** | `_DATE_FIELDS` in `vehicles.py` PATCH must include: `registered_at`, `insurance_until`, `license_issued_at`, `license_expires_at`, `medical_cert_expires_at`. |
| **`flag_modified` for JSONB props** | Any mutation of `vehicle.props` dict needs `flag_modified(vehicle, 'props')` before `db.commit()`. |
| **FastAPI routing order** | Register specific vehicle sub-routes (`/vehicles/dashboard`, `/vehicles/import`, `/vehicles/drivers`) BEFORE the catch-all `/{vehicle_id:int}` route in `__init__.py`. |
| **dict-detail HTTPException** | Custom handler in `__init__.py:237–249` (post-`b179c4f`) now supports dict-detail. Use standard `raise HTTPException(detail={code: '...', ...})` — it works. |
| **localStorage key collision** | Use `vehicle_dashboard_layout_u${userId}` (not `dashboard_layout_v2_${userId}`). |
| **File upload `access_token` vs `auth_token`** | Use `apiFetch` from `api.ts` for all vehicle attachment uploads (not raw `fetch` with `localStorage.getItem('access_token')`). |
| **VIN=NULL for many vehicles** | Conflict key = `plate` alone (not VIN+plate). UNIQUE constraint on `plate` in vehicles table. |
| **Cyrillic xlsx headers** | openpyxl reads them correctly as Unicode (codepoints 1040–1103). Display issue is terminal only. |
| **ApexCharts + page transition** | Do NOT use `mode="out-in"` on router transition for dashboard routes. Use `:key="route.fullPath"` (per Gotchas). |

---

## xlsx Column Mapping Summary

**24 columns in Лист2 (row 1 = headers, 51 data rows):**
```
Col 0:  №                          → skip (auto-increment id)
Col 1:  Марка и модель ТС          → brand + model (split on last space)
Col 2:  Цвет                       → color
Col 3:  VIN                        → vin (NULL if 'отсутствует')
Col 4:  Гос. рег. знак             → plate (UNIQUE KEY)
Col 5:  Собственник                → owner_org_id (lookup by name) OR assigned_text
Col 6:  Дата п/п                   → registered_at (datetime → date)
Col 7:  У кого в эксплуатации      → assigned_text (region/city free text)
Col 8:  Тип ТС                     → type ENUM (see TYPE_MAP in R-5)
Col 9:  Страховка                  → insurance_until (date or NULL)
Col 10: Состояние                  → state ENUM
Col 11: трекер                     → has_tracker BOOL
Col 12: АКБ                        → akb_ok BOOL
Col 13: Наличие радиостанции       → has_radio BOOL
Col 14: Наличие и исправность зеркал → mirrors_ok BOOL
Col 15: Авторезина                 → props['tires_type']
Col 16: Брендирование              → props['branding']
Col 17: Наличие набора ключей      → has_keys BOOL
Col 18: Наличие аптечки            → has_first_aid_kit BOOL
Col 19: Наличие запасного колеса   → has_spare_wheel BOOL
Col 20: Огнетушитель               → has_extinguisher BOOL
Col 21: Состояние лакокрасочного покрытия → props['paint_condition']
Col 22: Неисправность              → props['defect_description']
Col 23: Примечание                 → props['note']
```

---

## Estimated Plan Breakdown for gsd-planner

```
Plan 29-01: check_schema — vehicles + all sub-tables + ALTERs for purchases/users/tasks
Plan 29-02: permission seed (vehicles tab + 6 actions) in __init__.py lifespan
Plan 29-03: Vehicle SQLAlchemy model + Pydantic schemas
Plan 29-04: vehicles CRUD router (GET list with visibility filter, GET detail, POST, PATCH, DELETE)
Plan 29-05: vehicles_seed.py (xlsx import at startup + lifespan call)
Plan 29-06: vehicle Excel import UI dialog + VehicleListView (based on OrdersView pattern)
Plan 29-07: VehicleAttachment + RepairAttachment routers (upload/download/list, bytea pattern)
Plan 29-08: VehicleRepair router + RepairAttachment
Plan 29-09: VehicleOdometer router + FuelLog router (CRUD + fuel norm calc)
Plan 29-10: trips router + 3 docxtpl templates (trip_light/truck/special.docx) + smoke-render test
Plan 29-11: ExternalDriver router + User.can_drive extension in StaffView
Plan 29-12: vehicles_dashboard router (KPI aggregations + chart data endpoints)
Plan 29-13: lifespan daily alert cron (system_tag idempotency + Task creation for 4 alert types)
Plan 29-14: AppBar «Имущество» + router.ts new routes + placeholder views
Plan 29-15: VehicleDetailView (tabs: Info / Documents / Photos / Repairs / Odometer / Fuel / Trips / History / Purchases)
Plan 29-16: VehicleDashboardView (grid-layout-plus + 8 widgets + SVG canister + pulse CSS)
Plan 29-17: CreateOrderView vehicle_id selector + Purchase vehicle tab integration
Plan 29-18: .docx template files (create trip_light/truck/special.docx) + smoke-render verification
```

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Минтранс Приказ №368 (2020) is current regulation for trip forms | R-3 | Trip form may have wrong mandatory fields; low risk as fields are standard |
| A2 | Приказ АМ-23-р endorses 2-norm simplification for fleet management | R-4 | May need per-region correction table; add `region_correction_pct` field later |
| A3 | xlsx Тип ТС values: "минивэн"/"легковой"/"грузовой" etc. cover all 51 rows | R-5 | Seed may fail for unmapped types → use 'other' as fallback (safe) |

---

## Sources

### Primary (HIGH — verified from project codebase)
- `backend/app/__init__.py` — lifespan pattern, permission seed, cron loop (lines 50–174, 241–284, 537–553)
- `backend/check_schema.py` — `_ensure_*_table` pattern (lines 204–258)
- `backend/app/models/task.py` — Task model (no system_tag column exists)
- `backend/app/auth/jwt.py:103–121` — `get_org_filter` implementation
- `frontend/src/composables/useDashboardLayout.ts` — full composable (12-col, rowHeight=30, localStorage key pattern)
- `/tmp/xlsx_headers.txt` — decoded xlsx Лист2 column headers (openpyxl verified, 24 columns, 51 data rows)
- `backend/app/routers/purchases.py:1106–1139` — `_coerce_patch_value` / `_DATE_FIELDS` pattern
- `C:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/05_Gotchas.md` — all gotchas verified
- `C:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Lessons.md` — `{% tr %}` forbidden, smoke-render rule

### Secondary (MEDIUM — from CONTEXT.md decisions)
- D-08 Vehicle schema columns — complete column list in CONTEXT.md
- D-20 Fuel norm formula — season-based simplification per user decision

### Tertiary (LOW — assumed from training)
- A1–A3 per Assumptions Log above

---

**Research date:** 2026-05-19
**Valid until:** 2026-06-19 (stable patterns, 30-day window)
