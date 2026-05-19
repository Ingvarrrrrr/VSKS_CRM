# Phase 29 — Vehicle Fleet — Plan Index

**Created:** 2026-05-19
**Total plans:** 21
**Waves:** 0..5

## Wave structure

| Wave | Plans | Parallelism |
|------|-------|-------------|
| 0 | 29-01, 29-02, 29-03 | Sequential (schema → migration → permissions) |
| 1 | 29-04..29-10 | Parallel (different routers, no file overlap) |
| 1.5 | 29-11, 29-12, 29-13 | Parallel (seed + import + cron, independent) |
| 2 | 29-14, 29-15, 29-16 | Parallel (different frontend files) |
| 3 | 29-17 | Sequential (large detail view) |
| 3.5 | 29-18 | Sequential (depends on 29-17 shell) |
| 4 | 29-19 | After backend dashboard endpoint |
| 5 | 29-20, 29-21 | Last (purchase integration + .docx templates) |

## Plan table

| # | Title | Wave | Deps | Complexity | Decisions |
|---|-------|------|------|------------|-----------|
| 29-01 | Backend models (9 SQLAlchemy + Pydantic) | 0 | none | L | D-04 D-06 D-07 D-08 D-10 D-11 D-12 D-13 D-15 D-18 |
| 29-02 | check_schema._ensure_* + ALTER (purchases/users/tasks) | 0 | 29-01 | L | D-06 D-08 D-13 D-17 D-18 |
| 29-03 | Permission seed (vehicles tab + 6 actions) | 0 | 29-02 | S | D-05 |
| 29-04 | Backend router vehicles.py (CRUD + visibility + history) | 1 | 29-02 29-03 | L | D-06 D-08 D-10 |
| 29-05 | vehicle_attachments + repair_attachments (bytea) | 1 | 29-02 29-03 | M | D-07 D-11 D-12 |
| 29-06 | vehicle_repairs router | 1 | 29-02 29-03 | M | D-12 D-18 |
| 29-07 | vehicle_odometer + fuel_logs routers | 1 | 29-02 29-03 | M | D-13 D-20 |
| 29-08 | trips router + docx render endpoint | 1 | 29-02 29-03 | M | D-14 D-19 |
| 29-09 | external_drivers + User.can_drive PATCH | 1 | 29-02 29-03 | M | D-04 D-15 |
| 29-10 | vehicles_dashboard router (KPIs + charts) | 1 | 29-02 29-03 | M | D-16 D-17 D-18 |
| 29-11 | vehicles_seed.py (xlsx Голичкова) | 1.5 | 29-02 | M | D-09 |
| 29-12 | vehicles_import.py router + region→org dialog | 1.5 | 29-04 29-11 | M | D-06 D-09 |
| 29-13 | lifespan daily alerts task | 1.5 | 29-02 | M | D-17 |
| 29-14 | AppBar «Имущество» + routes + placeholders | 2 | 29-03 | S | D-02 D-05 |
| 29-15 | StaffView extension (can_drive + license) | 2 | 29-02 | S | D-04 |
| 29-16 | VehicleListView (OrdersView pattern) | 2 | 29-04 29-12 | L | D-02 D-06 D-09 |
| 29-17 | VehicleDetailView shell + 9 tabs + history popover | 3 | 29-04 29-14 | L | D-08 D-10 |
| 29-18 | Tab components (attach/photo/repair/odo/fuel/trip/purchase) | 3.5 | 29-05..29-09 29-17 | L | D-07 D-11 D-12 D-13 D-14 D-15 D-18 |
| 29-19 | VehicleDashboardView + 11 widgets | 4 | 29-10 29-14 | L | D-16 |
| 29-20 | documents.py extension + 3 trip docx файла | 5 | 29-08 | M | D-14 D-19 |
| 29-21 | CreateOrderView vehicle_id selector | 5 | 29-04 29-14 | S | D-18 |

## Source-Item Coverage Audit

### Decisions (from 29-CONTEXT.md)

| Decision | Covered by |
|----------|------------|
| D-01 Full GSD workflow | meta — this plan set |
| D-02 AppBar «Имущество» + routes | 29-14, 29-16 |
| D-03 Full fuel+mileage tracking | 29-01, 29-07, 29-08, 29-18 |
| D-04 User.can_drive + license_* | 29-01, 29-02, 29-09, 29-15 |
| D-05 Permission tab + 6 actions | 29-03, 29-14 |
| D-06 Multi-tenancy visibility | 29-01, 29-04, 29-11, 29-12, 29-16 |
| D-07 bytea attachments + SHA-256 | 29-01, 29-05, 29-18 |
| D-08 Mixed schema + JSONB props | 29-01, 29-02, 29-04, 29-17 |
| D-09 xlsx seed + UI import | 29-11, 29-12, 29-16 |
| D-10 VehicleFieldHistory | 29-01, 29-04, 29-17 |
| D-11 Document slots ENUM | 29-01, 29-05, 29-18 |
| D-12 VehicleRepair + RepairAttachment | 29-01, 29-05, 29-06, 29-18 |
| D-13 VehicleOdometer absolute + UNIQUE | 29-01, 29-02, 29-07, 29-18 |
| D-14 3 docx templates by type | 29-08, 29-18, 29-20 |
| D-15 ExternalDriver | 29-01, 29-09, 29-18 |
| D-16 8+ draggable widgets | 29-10, 29-19 |
| D-17 Auto-Tasks 30 days before expiry | 29-02, 29-10, 29-13 |
| D-18 Purchase.vehicle_id | 29-01, 29-02, 29-06, 29-18, 29-21 |
| D-19 .docx only trip output | 29-08, 29-18, 29-20 |
| D-20 Summer/winter fuel norms | 29-01, 29-07 |

### Research items (from RESEARCH.md)

| Research | Recommendation reflected in |
|----------|------------------------------|
| R-1 lifespan cron + Task.system_tag | 29-02 (ALTER tasks), 29-13 (daily loop) |
| R-2 SVG canister + pulse-glow CSS | 29-19 |
| R-3 docxtpl selector + smoke-render | 29-08, 29-20 |
| R-4 Russian fuel norm formula | 29-07 |
| R-5 idempotent seed + xlsx mapping | 29-11 |
| R-6 check_schema._ensure_* | 29-02 |
| R-7 grid-layout-plus + useDashboardLayout | 29-19 |
| R-8 explicit history logging in endpoint | 29-04 |
| R-9 programmatic permission seed | 29-03 |
| R-10 get_org_filter visibility | 29-04, 29-11, 29-12 |
| R-11 route autocomplete (history-based) | 29-18 |
| R-12 pulse animation intensities | 29-19 |

### Patterns (from 29-PATTERNS.md — Create list)

| New file | Plan |
|----------|------|
| backend/app/models/vehicle.py | 29-01 |
| backend/app/models/vehicle_attachment.py | 29-01 |
| backend/app/models/vehicle_repair.py | 29-01 |
| backend/app/models/repair_attachment.py | 29-01 |
| backend/app/models/vehicle_field_history.py | 29-01 |
| backend/app/models/vehicle_odometer.py | 29-01 |
| backend/app/models/fuel_log.py | 29-01 |
| backend/app/models/trip.py | 29-01 |
| backend/app/models/external_driver.py | 29-01 |
| backend/app/routers/vehicles.py | 29-04 |
| backend/app/routers/vehicle_attachments.py | 29-05 |
| backend/app/routers/repair_attachments.py | 29-05 |
| backend/app/routers/vehicle_repairs.py | 29-06 |
| backend/app/routers/vehicle_odometer.py | 29-07 |
| backend/app/routers/fuel_logs.py | 29-07 |
| backend/app/routers/trips.py | 29-08 |
| backend/app/routers/external_drivers.py | 29-09 |
| backend/app/routers/vehicles_dashboard.py | 29-10 |
| backend/app/routers/vehicles_import.py | 29-12 |
| backend/app/services/vehicles_seed.py | 29-11 |
| backend/templates/trip_light.docx | 29-20 |
| backend/templates/trip_truck.docx | 29-20 |
| backend/templates/trip_special.docx | 29-20 |
| frontend/src/views/property/VehicleListView.vue | 29-16 |
| frontend/src/views/property/VehicleDetailView.vue | 29-17 |
| frontend/src/views/property/VehicleDashboardView.vue | 29-19 |
| frontend/src/views/property/EquipmentPlaceholderView.vue | 29-14 |
| frontend/src/views/property/MiscPlaceholderView.vue | 29-14 |
| frontend/src/components/vehicles/VehicleAttachmentSlot.vue | 29-18 |
| frontend/src/components/vehicles/VehiclePhotosTab.vue | 29-18 |
| frontend/src/components/vehicles/RepairsTab.vue | 29-18 |
| frontend/src/components/vehicles/OdometerTab.vue | 29-18 |
| frontend/src/components/vehicles/FuelLogTab.vue | 29-18 |
| frontend/src/components/vehicles/TripsTab.vue | 29-18 |
| frontend/src/components/vehicles/RelatedPurchasesTab.vue | 29-18 |
| frontend/src/components/vehicles/FieldHistoryPopover.vue | 29-17 |
| frontend/src/components/vehicles/FuelCanisterWidget.vue | 29-19 |
| frontend/src/components/vehicles/MaintenanceWarningWidget.vue | 29-19 |
| frontend/src/components/vehicles/VehiclesInRepairWidget.vue | 29-19 |

No items missing.

## Universal boilerplate for every plan

Every plan ends with these executor instructions:

1. **No verification loops.** Executor MUST NOT run `docker exec`, `alembic upgrade`, `npm run build`, `pytest`, `playwright` in loops. Commit + push + stop. Autodeploy verifies.
2. **Verify push.** Run `git log origin/claude..HEAD` after each commit to confirm push went through.
3. **Pre-push grep for frontend.** Before pushing any `.vue` / `.ts` change with multiple `let`/`const`: `grep -cE '^(let|const) <name>\b' <file>` — must be 1, else rename.
4. **Smoke-render docx.** Any new `.docx` template — render with fake_dict via `DocxTemplate(path).render(fake_dict)` before commit (Lesson 2026-05-18).
5. **Date column = _DATE_FIELDS.** Any new `Column(Date)` or `Column(DateTime)` — add field name to `_DATE_FIELDS` in PATCH endpoint.
6. **JSONB mutation = flag_modified.** Any mutation of dict/list inside JSONB column — `from sqlalchemy.orm.attributes import flag_modified; flag_modified(obj, 'field')` before commit.
7. **ENUM idempotency.** New ENUM types — DO block (`DO $$ BEGIN CREATE TYPE ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;`) — PG не поддерживает `CREATE TYPE IF NOT EXISTS`.
8. **No generic snackbar.** Any new error UI path — show `code` + `message` + `correlation_id` (when present) — not generic «Ошибка».
9. **Recent-commit check.** Before push of DB schema changes (Column(...) in model): `git log origin/claude..HEAD` — если есть unpushed model changes без applied `_ensure_*_table`, рискуем 502.
