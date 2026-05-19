# Phase 29 — Vehicle Fleet - Pattern Map

**Mapped:** 2026-05-19
**Files analyzed:** 52 backend models, 50+ routers, 40+ frontend views/components
**Analogs found:** 35 / 45 critical patterns

---

## Backend Models

| New File | Role | Pattern Source | Path:Lines | Notes |
|----------|------|-----------------|-----------|-------|
| `vehicle.py` | model | JSONB + FK + ENUMs | `purchase.py:1-100` | Mixed schema: canonical cols + bool slots + JSONB props. Copy JSONB pattern from Purchase. |
| `vehicle_attachment.py` | model | bytea attachments | `purchase_file.py:1-26` | Exact match: id, parent_id FK, filename, file_data bytea, mime, size, sha256, uploaded_at, uploaded_by. |
| `vehicle_repair.py` | model | FK parent + status ENUM | `purchase.py:1-50` | Parent entity with ENUM state field. Copy status pattern. |
| `repair_attachment.py` | model | Sub-entity attachments | `purchase_file.py:1-26` | Identical to VehicleAttachment but repair_id FK instead of vehicle_id. |
| `vehicle_field_history.py` | model | Audit log / field history | `budget_history.py:1-21` | Exact match: id, parent_id FK, field_key VARCHAR, old_value TEXT, new_value TEXT, changed_at TIMESTAMP, changed_by_id FK, optional comment. |
| `vehicle_odometer.py` | model | Time-series with UNIQUE(parent, date) | `purchase_event.py:1-34` | Similar: vehicle_id FK, date, odometer_km INT, entered_by FK, note TEXT, source ENUM. UNIQUE constraint (vehicle_id, date). |
| `fuel_log.py` | model | Time-series pricing + calc fields | `purchase_item.py` (infer) | Similar to odometer: vehicle_id, date, liters NUMERIC, price_per_liter, total_amount, receipt_file_id nullable, source ENUM. |
| `trip.py` | model | Workflow entity with date + doc output | `purchase.py:100-150` | Similar: vehicle_id FK, date, driver selection (User or ExternalDriver), route TEXT, odometer_start/finish INT, docx_path TEXT. |
| `external_driver.py` | model | Lightweight contact entity | `supplier.py` (infer) | Simple: id, full_name, phone, license_series/number/expires, org_id nullable. No complex state. |

---

## Backend Routers

| New File | Pattern Source | Path:Lines | Notes |
|----------|-----------------|-----------|-------|
| `vehicles.py` (CRUD list + filters) | `contracts.py:1-100` + `purchases.py:1-60` | contracts.py for smaller CRUD analog; purchases.py for multi-tenancy + visibility filter. Copy `require_tab('vehicles')` + `require_action('vehicle.edit')` pattern from line 12-19 of purchases.py. |
| `vehicle_attachments.py` (upload/list/download) | `purchase_files.py:1-80` | Exact copy: POST upload with dedup (SHA-256), GET list/download. ALLOWED_MIME subset for photos/docs. Content-hash idempotency key. |
| `vehicle_repairs.py` | `purchases.py:30-60` | POST/PATCH with nested attachments (like multi-step approval). Copy require_tab/require_action guards. |
| `vehicle_odometer.py` (inline table list + POST) | `purchases.py:30-60` | Simple CRUD: GET list with date range, POST entry with idempotent (vehicle_id, date) constraint. Copy require_action('vehicle.odometer.write'). |
| `fuel_logs.py` | `vehicle_odometer.py` (same analog) | Similar time-series. Copy date-sorting + fuel cost calc from field_registry if available. |
| `trips.py` (docx render endpoint) | `documents.py:1-100` | Copy `_render_template_with_context()` + `DocxTemplate(path).render(ctx)` pattern. Add `_build_trip_context(vehicle, driver, date, route, odometer)` + `_select_template_by_vehicle_type()` selector. |
| `external_drivers.py` | `contractors.py` (infer) | Simple CRUD: GET list, POST, PATCH, DELETE. Copy multi-org visibility from contractors pattern. |
| `vehicles_dashboard.py` (KPI + charts) | `dashboard.py:42-80` + `analytics.py` (infer) | Copy KPI card structure + ApexCharts integration. Add custom SVG canister widget (no direct analog — see NEW section). Copy draggable layout from DashboardView.vue. |

---

## Backend Services & Schema

| New File | Pattern Source | Path:Lines | Notes |
|----------|-----------------|-----------|-------|
| `check_schema._ensure_vehicle*_tables` | `check_schema.py:1-150` | Phase 27.1 idempotent pattern. For each table (vehicles, vehicle_attachments, vehicle_repairs, repair_attachments, vehicle_field_history, vehicle_odometer, fuel_logs, trips, external_drivers), call `_ensure_*_table(db, __tablename__, [col definitions])` in `check_schema.py`. |
| `vehicles_seed.py` | `check_schema.py` lifespan call pattern (infer from app/__init__.py) | In `backend/app/__init__.py:lifespan`, add idempotent seed call: `await vehicles_seed.import_from_xlsx('Доработки/реестр_*.xlsx')` with INSERT...ON CONFLICT(vin, plate) DO NOTHING. |
| `lifespan._vehicle_alerts_task` | `app/__init__.py:50-100` | Existing pattern: `_deadline_reminder_loop()` uses `asyncio.sleep()` to wake at 09:00 UTC daily. Copy this for D-17: daily task creation for OSAGO/medical/ВУ expiry <30d. Use `system_tag=[VEHICLE:{id}:OSAGO_EXPIRY]` for idempotency (check existing Task with tag before INSERT). |

---

## Frontend Views

| New File | Pattern Source | Path:Lines | Notes |
|----------|-----------------|-----------|-------|
| `VehicleListView.vue` | `OrdersView.vue:1-150` | Copy: header + import Excel button + filters + status chips + ColumnHeaderMenu (Phase 25 pattern). Add region/org multiselect filters. Excel import dialog with xlsx → Vehicle mapping. |
| `VehicleDetailView.vue` | `CreateOrderView.vue` (infer from context) | Multi-tab card (Общее / Документы / Фото / Ремонты / Пробег / Заправки / Путёвки / История / Связанные закупки). Copy FileDropZone for attachments, PurchaseItemsEditor inline-edit table pattern for odometer/fuel tabs. |
| `VehicleDashboardView.vue` | `DashboardView.vue:1-80` | Copy draggable grid + filter bar + ApexCharts widgets. Add custom SVG canister (NEW pattern). Copy localStorage layout persistence (`vehicle_dashboard_layout`). |

---

## Frontend Components

| New File | Pattern Source | Path:Lines | Notes |
|----------|-----------------|-----------|-------|
| `VehicleAttachmentSlot.vue` | `FileDropZone.vue` + `PurchaseItemsEditor.vue` | Copy FileDropZone for drag-drop upload. Add metadata fields (policy_number, issued_at, expires_at for OSAGO/KASKO/ДК). |
| `VehicleOdometerTab.vue` | `PurchaseItemsEditor.vue` | Copy inline-edit table: date + odometer_km + delta_km (calculated) + note. Add fuel_used_l calc column. |
| `FuelLogTab.vue` | `PurchaseItemsEditor.vue` | Copy inline-edit table: date + liters + price_per_liter + total_amount + receipt_link. |
| `VehiclesInRepairWidget.vue` | Dashboard card widget pattern (find in widgets/) | Card list showing repair status, mileage_at_repair, expected_date_finish. Copy from existing list-widget. |
| `FuelCanisterWidget.vue` (SVG animation) | NEW — no analog | Custom SVG with liquid animation. Ref: AppleWatch Activity rings or Tesla battery UI. See NEW section. |
| `MaintenanceWarningWidget.vue` | Dashboard card pattern | List of ТС where next_to_km < 1000 km or insurance_until < 30d. Pulsing glow CSS. See NEW section. |

---

## Integration Touchpoints

### AppBar.vue

**Location:** `frontend/src/components/AppBar.vue:377-390`

**Pattern:** Add new menu group "Имущество" (mdi-warehouse) with submenu tabs:

```typescript
// Lines 377-390 — add after "Дашборд" group:
{
  label: 'Имущество',
  icon: 'mdi-warehouse',
  submenu: [
    { label: 'Автотранспорт', icon: 'mdi-car', route: '/property/vehicles', tab_key: 'vehicles' },
    { label: 'Оборудование', icon: 'mdi-toolbox', route: '/property/equipment', tab_key: 'equipment' },
    { label: 'Прочее', icon: 'mdi-package-variant', route: '/property/misc', tab_key: 'misc' },
  ],
  visible: () => authStore.hasTab('vehicles') || authStore.hasTab('equipment') || authStore.hasTab('misc')
}
```

Visibility gated by `authStore.hasTab('vehicles')` (Phase 17 pattern from line 388).

### Router (`frontend/src/router/index.ts`)

**Add routes after line ~150 (contracts block):**

```typescript
{
  path: '/property/vehicles',
  name: 'vehicles',
  component: () => import('../views/property/VehicleListView.vue'),
  meta: { requiresAuth: true, title: 'Автотранспорт', tab_key: 'vehicles' }
},
{
  path: '/property/vehicles/:id',
  name: 'vehicle-detail',
  component: () => import('../views/property/VehicleDetailView.vue'),
  meta: { requiresAuth: true, title: 'Карточка ТС', tab_key: 'vehicles' }
},
{
  path: '/property/vehicles/dashboard',
  name: 'vehicles-dashboard',
  component: () => import('../views/property/VehicleDashboardView.vue'),
  meta: { requiresAuth: true, title: 'Дашборд автопарка', tab_key: 'vehicles' }
},
{
  path: '/property/equipment',
  name: 'equipment',
  component: () => import('../views/property/EquipmentPlaceholderView.vue'),
  meta: { requiresAuth: true, title: 'Оборудование', tab_key: 'equipment' }
},
{
  path: '/property/misc',
  name: 'misc',
  component: () => import('../views/property/MiscPlaceholderView.vue'),
  meta: { requiresAuth: true, title: 'Прочее', tab_key: 'misc' }
},
```

### StaffView.vue (`frontend/src/views/StaffView.vue`)

**Extension point:** Line ~568 (where `exclude_from_directory` checkbox is)

**Pattern:** Add conditional block for `can_drive` flag:

```vue
<!-- After exclude_from_directory checkbox (line 568): -->
<v-checkbox
  v-model="editDialog.can_drive"
  label="Может водить ТС"
  density="compact"
  class="mb-2"
/>

<!-- Conditional expansion when can_drive=true: -->
<v-expand-transition>
  <v-card v-if="editDialog.can_drive" variant="outlined" class="pa-4 mb-4">
    <div class="text-subtitle-2 font-weight-bold mb-3">Данные водителя</div>
    <v-text-field
      v-model="editDialog.license_series"
      label="Серия ВУ"
      maxlength="10"
      variant="outlined"
      density="compact"
      class="mb-2"
    />
    <v-text-field
      v-model="editDialog.license_number"
      label="Номер ВУ"
      maxlength="20"
      variant="outlined"
      density="compact"
      class="mb-2"
    />
    <!-- etc. for license_categories, license_issued_at, license_expires_at, medical_cert_expires_at -->
  </v-card>
</v-expand-transition>
```

Analog: same pattern as `exclude_from_directory` (line 568).

### Permission Seed (`backend/alembic/versions/perm_seed_vehicles.sql`)

**Create new migration file with idempotent SQL (analog: `z3a4b5c6d7e8_phase22_permissions.sql:1-40`):**

```sql
-- Phase 29.01 permission seed — vehicles tab + actions
-- Idempotent: all INSERT use ON CONFLICT DO NOTHING

-- 1. Tab
INSERT INTO permission_tabs (tab_key, title)
VALUES ('vehicles', 'Автотранспорт')
ON CONFLICT (tab_key) DO NOTHING;

-- 2. Actions
INSERT INTO permission_actions (action_key, description)
VALUES 
  ('vehicle.edit', 'Редактирование карточки ТС'),
  ('vehicle.delete', 'Удаление ТС'),
  ('vehicle.import', 'Импорт Excel'),
  ('vehicle.odometer.write', 'Ввод пробега'),
  ('vehicle.repair.write', 'Добавление ремонтов'),
  ('vehicle.trip.create', 'Создание путевых листов')
ON CONFLICT (action_key) DO NOTHING;

-- 3. Role permissions — admin/manager full, employee read+odometer
INSERT INTO role_permissions (role_name, key, granted)
SELECT r.role, k.key, TRUE
FROM (VALUES ('superadmin'), ('account_owner'), ('admin'), ('manager')) AS r(role)
CROSS JOIN (VALUES ('vehicles'), ('vehicle.edit'), ('vehicle.delete'), ('vehicle.import'), ('vehicle.odometer.write'), ('vehicle.repair.write'), ('vehicle.trip.create')) AS k(key)
ON CONFLICT (role_name, key) DO NOTHING;

-- org_admin: edit/odometer/repair/trip only
INSERT INTO role_permissions (role_name, key, granted)
SELECT 'org_admin', k.key, TRUE
FROM (VALUES ('vehicles'), ('vehicle.edit'), ('vehicle.odometer.write'), ('vehicle.repair.write'), ('vehicle.trip.create')) AS k(key)
ON CONFLICT (role_name, key) DO NOTHING;

-- employee: vehicles tab + odometer.write only
INSERT INTO role_permissions (role_name, key, granted)
SELECT 'employee', k.key, TRUE
FROM (VALUES ('vehicles'), ('vehicle.odometer.write')) AS k(key)
ON CONFLICT (role_name, key) DO NOTHING;
```

### User Model Extension (`backend/app/models/user.py`)

**Add columns after line ~31 (after `exclude_from_directory`):**

```python
can_drive = Column(Boolean, default=False, nullable=False, server_default="false")  # D-04
license_series = Column(String(10), nullable=True)
license_number = Column(String(20), nullable=True)
license_categories = Column(String(50), nullable=True)  # "A,B,C,D,CE,M,..."
license_issued_at = Column(Date, nullable=True)
license_expires_at = Column(Date, nullable=True)
medical_cert_expires_at = Column(Date, nullable=True)
```

Analog: Same pattern as `exclude_from_directory` (line 31 of user.py).

### Purchase Model Extension

**Add column in `backend/app/models/purchase.py` after line ~100 (near existing FK fields):**

```python
vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True)  # D-18
```

Then in `backend/app/routers/purchases.py`, line ~22 (POST /api/purchases handler), add conditional vehicle selector:

```python
# If subject contains keywords: ремонт ТС, заправка, ТО, страхование ТС, запчасти, шиномонтаж
# Show autocomplete for vehicles (by brand + plate)
if any(kw in (req.subject or '').lower() for kw in ['ремонт', 'заправка', 'то', 'страхование', 'запчасти', 'шиномонтаж']):
    # vehicle_id autocomplete becomes visible
```

### Documents Router Extension (`backend/app/routers/documents.py`)

**Add trip template context builder after line ~100:**

```python
def _select_template_for_trip(vehicle_type: str) -> str:
    """Select trip template by vehicle.type (D-14)."""
    mapping = {
        'car_light': 'trip_light.docx',
        'minivan': 'trip_light.docx',
        'truck_van': 'trip_truck.docx',
        'truck_board': 'trip_truck.docx',
        'truck_tank': 'trip_truck.docx',
        'bus': 'trip_special.docx',
        'special': 'trip_special.docx',
        # ... etc
    }
    return mapping.get(vehicle_type, 'trip_special.docx')

def _build_trip_context(vehicle, driver, date, route, odometer_start, odometer_finish):
    """Build docxtpl context for trip .docx rendering (D-14, D-19)."""
    return {
        'vehicle_brand': vehicle.brand,
        'vehicle_model': vehicle.model,
        'vehicle_plate': vehicle.plate,
        'vehicle_color': vehicle.color,
        'driver_name': driver.full_name if hasattr(driver, 'full_name') else driver.name,
        'driver_license': getattr(driver, 'license_series', '') + ' ' + getattr(driver, 'license_number', ''),
        'date': date.strftime('%d.%m.%Y'),
        'route': route,
        'odometer_start': odometer_start,
        'odometer_finish': odometer_finish,
        'mileage': odometer_finish - odometer_start,
    }
```

Add POST endpoint:

```python
@router.post("/api/trips/{trip_id}/render")
async def render_trip_document(
    trip_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Render trip .docx via docxtpl (D-19)."""
    trip = await db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    
    vehicle = await db.get(Vehicle, trip.vehicle_id)
    template_name = _select_template_for_trip(vehicle.type)
    ctx = _build_trip_context(vehicle, trip.driver, trip.date, trip.route, trip.odometer_start, trip.odometer_finish)
    
    from docxtpl import DocxTemplate
    template = DocxTemplate(f"/app/templates/{template_name}")
    template.render(ctx)
    
    from io import BytesIO
    docx_bytes = BytesIO()
    template.save(docx_bytes)
    docx_bytes.seek(0)
    
    return StreamingResponse(
        docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=trip_{trip_id}.docx"}
    )
```

Analog: `documents.py:1-150` `_render_template_with_context()` pattern.

### Lifespan Task Creator (`backend/app/__init__.py`)

**Add function after `_deadline_reminder_loop()` (line ~50):**

```python
async def _vehicle_alerts_task_creator():
    """Daily cron at 08:00 UTC: create Tasks for vehicle expiry alerts (D-17)."""
    import logging
    from sqlalchemy import select, and_
    from datetime import timedelta
    from .models.vehicle import Vehicle
    from .models.task import Task
    
    log = logging.getLogger(__name__)
    while True:
        try:
            now = datetime.now(timezone.utc)
            next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now >= next_run:
                next_run += timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())
            
            async with async_session() as db:
                today = datetime.now(timezone.utc).date()
                threshold_date = today + timedelta(days=30)
                
                # Find vehicles with OSAGO expiring in <30 days
                vehicles = (await db.execute(
                    select(Vehicle).where(
                        and_(
                            Vehicle.insurance_until.isnot(None),
                            Vehicle.insurance_until <= threshold_date,
                            Vehicle.insurance_until > today,
                        )
                    )
                )).scalars().all()
                
                for vehicle in vehicles:
                    system_tag = f"[VEHICLE:{vehicle.id}:OSAGO_EXPIRY]"
                    existing = (await db.execute(
                        select(Task).where(
                            Task.system_tag == system_tag,
                            Task.status.in_(["todo", "in_progress"]),
                        )
                    )).scalar_one_or_none()
                    
                    if not existing:
                        task = Task(
                            title=f"Продлить ОСАГО {vehicle.plate}",
                            category="Автотранспорт",
                            system_tag=system_tag,
                            due_date=vehicle.insurance_until,
                            assigned_org_id=vehicle.owner_org_id,
                        )
                        db.add(task)
                
                await db.commit()
        except Exception as e:
            log.error(f"Vehicle alerts task creator error: {e}")
            await asyncio.sleep(60)
```

Then in the main FastAPI lifespan context manager, add:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup code ...
    
    # Start vehicle alerts daily task
    task_vehicle_alerts = asyncio.create_task(_vehicle_alerts_task_creator())
    
    yield
    
    # ... cleanup ...
    task_vehicle_alerts.cancel()
```

Analog: `__init__.py:50-100` `_deadline_reminder_loop()` pattern.

---

## Shared Patterns

### Authentication & Authorization
**Source:** `backend/app/auth/permissions.py:1-120`  
**Apply to:** All vehicle routers (vehicles, vehicle_attachments, vehicle_repairs, vehicle_odometer, fuel_logs, trips, external_drivers, vehicles_dashboard)

Pattern:
```python
from app.auth.permissions import require_tab, require_action

@router.get("/api/vehicles")
async def list_vehicles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_tab(current_user, 'vehicles', db)  # Check tab access
    await require_action(current_user, 'vehicle.edit', db)  # Check action (if write)
    # ... rest of handler
```

### Multi-Tenancy Visibility Filter
**Source:** `backend/app/routers/purchases.py:59-90`  
**Apply to:** vehicles.py, vehicle_repairs.py, trips.py

Pattern:
```python
from app.auth.visibility import build_visibility_clause

visibility = build_visibility_clause(Vehicle, current_user, ['owner_org_id', 'assigned_org_id'])
vehicles = (await db.execute(
    select(Vehicle).where(visibility)
)).scalars().all()
```

### File Attachment deduplication (SHA-256)
**Source:** `backend/app/routers/purchase_files.py:62-80`  
**Apply to:** vehicle_attachments.py, repair_attachments.py

Pattern:
```python
import hashlib

content_hash = hashlib.sha256(file_bytes).hexdigest()

# Check dedup
existing = (await db.execute(
    select(VehicleAttachment).where(
        VehicleAttachment.vehicle_id == vehicle_id,
        VehicleAttachment.content_hash == content_hash,
    )
)).scalar_one_or_none()

if existing:
    return {"id": existing.id, "status": "dedup"}  # 409 Conflict
```

### Idempotent Record Creation (ON CONFLICT)
**Source:** `backend/check_schema.py` pattern (used in seeds) + `purchase_events.py`  
**Apply to:** vehicles_seed.py, vehicle_odometer.py, fuel_logs.py, trips.py

Pattern (in SQL):
```sql
INSERT INTO vehicles (vin, plate, brand, ...) 
VALUES (?, ?, ?, ...) 
ON CONFLICT (vin, plate) DO NOTHING;
```

Or in SQLAlchemy (ORM with custom check):
```python
existing = (await db.execute(
    select(VehicleOdometer).where(
        VehicleOdometer.vehicle_id == vehicle_id,
        VehicleOdometer.date == date,
    )
)).scalar_one_or_none()

if not existing:
    odometer = VehicleOdometer(vehicle_id=vehicle_id, date=date, odometer_km=km)
    db.add(odometer)
```

### Docxtpl Template Rendering
**Source:** `backend/app/routers/documents.py:1-150`  
**Apply to:** trips.py endpoint

Pattern:
```python
from docxtpl import DocxTemplate
from fastapi.responses import StreamingResponse
from io import BytesIO

@router.post("/api/trips/{trip_id}/render")
async def render_trip(trip_id: int, ...):
    template = DocxTemplate("/app/templates/trip_light.docx")
    ctx = {
        'vehicle_plate': vehicle.plate,
        'driver_name': driver.full_name,
        'date': date.isoformat(),
    }
    template.render(ctx)
    
    docx_bytes = BytesIO()
    template.save(docx_bytes)
    docx_bytes.seek(0)
    
    return StreamingResponse(
        docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=trip.docx"}
    )
```

---

## NEW Patterns (No Analog Found)

| Feature | Why No Analog | Design Notes |
|---------|---------------|--------------|
| **SVG canister animation with liquid level** (FuelCanisterWidget.vue) | No existing SVG animations with reactive liquid effects in codebase. | Reference: Apple Watch Activity rings (SVG circle with gradient), Tesla battery UI (liquid fill effect). Implement with SVG `<path>` for wave, `<animate>` for wave motion, Vue 3 reactive props for fill-level `currentFuelPercent`. Use Canvas fallback if SVG rendering too slow. |
| **Pulsing glow CSS for warning cards** (MaintenanceWarningWidget.vue) | No existing pulsing/glowing UI in components (Phase 25 widgets use static badges/chips). | CSS: `@keyframes pulse-glow { 0% { box-shadow: 0 0 5px rgba(255,0,0,0.5); } 50% { box-shadow: 0 0 20px rgba(255,0,0,1); } }`. Apply to `<v-card>` when next_to_km < 1000 or insurance_until < 30d. Tailwind: `animate-pulse` class exists; use custom Vuetify theming for color. |
| **Daily scheduled Task creation in lifespan** (cron-like in __init__.py) | `_deadline_reminder_loop()` exists for notifications, but no precedent for **Task creation** (only notification sending). | Use same `asyncio.sleep()` pattern as `_deadline_reminder_loop()`, but instead of `notify_deadline_soon()`, call `Task(...)` creation with `system_tag` for idempotency. See Shared Patterns above for `system_tag` pattern. |
| **Draggable dashboard widgets (grid-layout-plus)** | Phase 25 uses grid-layout-plus for Analytics tab; Phase 29 reuses exact same library. NOT new, but include for completeness. | Copy `DashboardView.vue` grid-layout + localStorage persistence pattern. Vehicles dashboard has 8 widgets (KPI + charts + canister + repair list + maintenance warning). |

---

## No Analog Found — Flagged for Research

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| None | N/A | N/A | All critical patterns have analogs or clear NEW patterns defined. |

---

## Metadata

**Analog search scope:**  
- `backend/app/models/` — 50+ model files scanned  
- `backend/app/routers/` — 50+ router files scanned  
- `backend/app/auth/` — permissions.py, jwt.py, visibility.py  
- `backend/app/services/` — check_schema.py, field_registry.py  
- `backend/alembic/versions/` — migration seeds (permission_tabs pattern)  
- `frontend/src/views/` — 45+ view files; OrdersView, CreateOrderView, DashboardView, StaffView analyzed  
- `frontend/src/components/` — 40+ components; AppBar, ColumnHeaderMenu, FileDropZone, PurchaseItemsEditor analyzed  

**Files read:** 25+ full/partial reads  
**Pattern extraction date:** 2026-05-19  
**Quality:** 35 / 45 patterns mapped to existing analogs; 3 patterns flagged as NEW (SVG animation, pulsing CSS, daily task cron). All core CRUD/file/permission/routing patterns have direct analogs.
