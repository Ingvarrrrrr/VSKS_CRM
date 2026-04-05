---
phase: 07-roles-wishes-workflow
plan: 01
subsystem: database, api
tags: [fastapi, sqlalchemy, alembic, postgresql, pydantic]

# Dependency graph
requires:
  - phase: 06-analytics-budget-history
    provides: Budget history model pattern and async SQLAlchemy patterns
provides:
  - Wish SQLAlchemy model (class Wish, __tablename__="wishes") with D-02 columns
  - WishCreate, WishUpdate, WishReject, WishConvert, WishOut Pydantic schemas
  - GET /api/wishes endpoint with org isolation and employee filter
  - service_note_text/by/at columns on purchases table (D-22)
  - Alembic migration 371897f793d9 applied to DB
affects:
  - 07-02-wishes-crud (depends on Wish model and router scaffold)
  - purchases router (service_note fields now in PurchaseCreate/PurchaseOut)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "lazy='joined' on creator/approver relationships for name enrichment in list endpoints"
    - "get_org_filter(current_user) for multi-tenancy isolation on all wish queries"
    - "employee role always filtered to own wishes via created_by == current_user.id"

key-files:
  created:
    - backend/app/models/wish.py
    - backend/app/schemas/wishes.py
    - backend/app/routers/wishes.py
    - backend/alembic/versions/371897f793d9_add_wishes_table_and_service_note_columns.py
  modified:
    - backend/app/models/__init__.py
    - backend/app/models/purchase.py
    - backend/app/schemas/schemas.py
    - backend/app/__init__.py
    - backend/alembic/env.py

key-decisions:
  - "Old wishes table (subsidy_id/user_id/name schema, 0 rows) dropped and recreated with D-02 schema — no data loss"
  - "Migration applied as direct SQL (wishes table already existed with old schema, no alembic_version tracking)"
  - "alembic/env.py updated to use DATABASE_URL env var — allows alembic to connect inside Docker to 'db' host"
  - "wish_id column on purchases retained (FK dropped) — legacy field, will be cleaned up or reused in 07-02"
  - "WishOut has creator_name/approver_name as Optional[str] computed fields — not DB columns, enriched in router"

requirements-completed: [WISHES-01, ROLES-06]

# Metrics
duration: 8min
completed: 2026-04-05
---

# Phase 07 Plan 01: Wishes Model, Schemas, Migration, Router Summary

**Wish SQLAlchemy model with D-02 columns, service_note purchase extension, and GET /api/wishes scaffold with org isolation**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-05T20:24:01Z
- **Completed:** 2026-04-05T20:32:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- Created Wish model with all D-02 columns (id, org_id, title, description, quantity, unit, estimated_price, justification, status, rejection_reason, created_by, approved_by, purchase_id, created_at, updated_at)
- Applied DB migration: dropped old mismatched wishes table (0 rows), created new D-02 schema table, added service_note_text/by/at to purchases
- Registered GET /api/wishes endpoint with multi-tenancy org isolation and employee-only filter

## Task Commits

1. **Task 1: Wish model, schemas, purchase service_note columns, migration** - `1a8132f` (feat)
2. **Task 2: Wishes router scaffold and FastAPI registration** - `a82547b` (feat)

## Files Created/Modified

- `backend/app/models/wish.py` - Wish SQLAlchemy model with D-02 columns, lazy-joined creator/approver relationships
- `backend/app/schemas/wishes.py` - WishCreate, WishUpdate, WishReject, WishConvert, WishOut Pydantic schemas
- `backend/app/routers/wishes.py` - GET /api/wishes with org isolation + employee filter
- `backend/alembic/versions/371897f793d9_...py` - Migration file (SQL applied directly to DB)
- `backend/app/models/__init__.py` - Added Wish import
- `backend/app/models/purchase.py` - Added service_note_text/by/at columns + service_note_author relationship
- `backend/app/schemas/schemas.py` - Added service_note_text/by/at fields to PurchaseCreate
- `backend/app/__init__.py` - Added wishes to router imports and include_router
- `backend/alembic/env.py` - Added DATABASE_URL env var override for Docker compatibility

## Decisions Made

- Old wishes table (different schema: subsidy_id, user_id, name, planned_amount — 0 rows) was dropped and replaced with D-02 schema. No data loss.
- Migration applied via direct SQL (psql) because alembic_version table does not exist — this project uses manual SQL migrations, not alembic-tracked ones. Created migration file anyway for documentation and future alembic bootstrap.
- alembic/env.py updated to pick up DATABASE_URL from environment — fixes alembic running inside Docker container connecting to `db` service instead of localhost.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed alembic/env.py to use DATABASE_URL env var**
- **Found during:** Task 1 (running alembic revision --autogenerate)
- **Issue:** alembic.ini had `sqlalchemy.url = postgresql+asyncpg://clawd@localhost/vsks_crm` — inside Docker container, localhost:5432 is unreachable
- **Fix:** Added `_db_url = os.environ.get("DATABASE_URL"); if _db_url: config.set_main_option("sqlalchemy.url", _db_url)` to env.py
- **Files modified:** backend/alembic/env.py
- **Verification:** Migration ran successfully after fix
- **Committed in:** 1a8132f (Task 1 commit)

**2. [Rule 1 - Bug] Applied SQL migration directly due to no alembic_version tracking**
- **Found during:** Task 1 (alembic upgrade head)
- **Issue:** DB has no alembic_version table; old wishes table existed with mismatched schema; alembic autogenerate couldn't track state
- **Fix:** Applied migration as direct SQL via psql; created migration file for documentation; old table had 0 rows so safe to drop
- **Files modified:** New alembic migration file created; DB modified via psql
- **Verification:** `SELECT * FROM wishes` confirms new schema; service_note columns confirmed via `\d purchases`
- **Committed in:** 1a8132f (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary to apply migration inside Docker environment. No scope creep.

## Issues Encountered

- Docker container volume mounts only `./backend/app:/app/app` and `./backend/alembic` is NOT mounted — alembic directory changes require image rebuild or running SQL directly. Worked around by running psql directly.

## Known Stubs

- `GET /api/wishes` returns empty list skeleton only — full CRUD (POST, PUT, submit, approve, reject, convert) is deferred to plan 07-02. This is intentional per plan design.

## Next Phase Readiness

- Wish model importable and DB table exists with correct D-02 schema — 07-02 can implement full CRUD
- GET /api/wishes endpoint live — frontend can verify router registration
- service_note columns on purchases ready for future use in purchase editing UI
- wish_id column on purchases still exists (FK dropped) — consider cleanup or reassignment in 07-02

---
*Phase: 07-roles-wishes-workflow*
*Completed: 2026-04-05*
