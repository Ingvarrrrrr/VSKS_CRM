# Phase 29 — Vehicle Fleet — MANIFEST

**Created:** 2026-05-19
**Phase:** 29-vehicle-fleet
**Total plans:** 21
**Source artifacts:**
- `c:\Users\1\Desktop\Cursor\VSKS_CRM\.planning\phases\29-vehicle-fleet\29-CONTEXT.md` (20 decisions D-01..D-20)
- `c:\Users\1\Desktop\Cursor\VSKS_CRM\.planning\phases\29-vehicle-fleet\29-PATTERNS.md` (35 analog mappings)
- `c:\Users\1\Desktop\Cursor\VSKS_CRM\.planning\phases\29-vehicle-fleet\RESEARCH.md` (R-1..R-12)

## Plan files

- `29-01-PLAN.md` — Backend models (9 SQLAlchemy models + Pydantic schemas)
- `29-02-PLAN.md` — check_schema._ensure_* для 9 таблиц + ALTER (Purchase/User/Task)
- `29-03-PLAN.md` — Permission seed (vehicles tab + 6 actions) программно в lifespan
- `29-04-PLAN.md` — Backend router vehicles.py (CRUD + multi-tenancy + PATCH + history hook)
- `29-05-PLAN.md` — vehicle_attachments.py + repair_attachments.py (bytea + SHA-256)
- `29-06-PLAN.md` — vehicle_repairs.py CRUD + linked Purchase
- `29-07-PLAN.md` — vehicle_odometer.py + fuel_logs.py (UNIQUE date + delta + fuel calc)
- `29-08-PLAN.md` — trips.py + 3 docxtpl шаблона + smoke-render
- `29-09-PLAN.md` — external_drivers.py + User.can_drive + driver-union endpoint
- `29-10-PLAN.md` — vehicles_dashboard.py (KPI + chart aggregations)
- `29-11-PLAN.md` — vehicles_seed.py (xlsx Голичкова → Vehicle, idempotent by plate)
- `29-12-PLAN.md` — vehicles_import.py router + region→org mapping dialog
- `29-13-PLAN.md` — lifespan daily alerts task (OSAGO/license/medical/TO_WARNING)
- `29-14-PLAN.md` — Frontend AppBar «Имущество» + 5 routes + placeholders
- `29-15-PLAN.md` — Frontend StaffView extension (can_drive + license_* + medical)
- `29-16-PLAN.md` — Frontend VehicleListView (OrdersView pattern + import button)
- `29-17-PLAN.md` — Frontend VehicleDetailView shell + 9 tabs + FieldHistoryPopover
- `29-18-PLAN.md` — Frontend tab components (Attachments/Photos/Repairs/Odometer/Fuel/Trips/Purchases)
- `29-19-PLAN.md` — Frontend VehicleDashboardView + 11 widgets + SVG canister + pulse-glow
- `29-20-PLAN.md` — Backend documents.py extension (trip_* DOC_TYPES) + 3 .docx файлов
- `29-21-PLAN.md` — Frontend CreateOrderView vehicle_id selector (conditional на subject keyword)
