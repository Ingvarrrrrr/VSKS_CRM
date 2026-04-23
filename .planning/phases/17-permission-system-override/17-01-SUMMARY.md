---
phase: 17-permission-system-override
plan: 01
subsystem: database
tags: [sqlalchemy, alembic, permissions, role-based-access, postgresql]

# Dependency graph
requires:
  - phase: 16-refactor-monoliths
    provides: clean FastAPI routers with require_role() pattern ready for migration
provides:
  - SQLAlchemy models: PermissionTab, PermissionAction, RolePermission, UserOrgPermissionOverride
  - Alembic migration q4r5s6t7u8v9 chained after p3q4r5s6t7u8 with idempotent seed
  - 23 permission_tabs rows (menu items as truth source from AppBar.vue)
  - 7 permission_actions rows (D-06 critical actions)
  - role_permissions seeded from ADMIN/MANAGER/ALL_ROLES hardcoded matrix (zero-regression D-05)
  - can_publish → publication.create UserOrgPermissionOverride migration per primary org
affects:
  - 17-02-PLAN (test scaffolds query these tables)
  - 17-03-PLAN (require_tab factory queries role_permissions)
  - 17-04-PLAN (permissions router CRUD)
  - 17-05-PLAN (frontend Pinia auth store)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Idempotent migration seed via INSERT INTO ... ON CONFLICT (key) DO NOTHING"
    - "user_org_access_id FK (not user_id+org_id pair) for per-org permission overrides"
    - "Boolean flip override mechanics: effective = overrides.get(key, role_permissions[role][key])"

key-files:
  created:
    - backend/app/models/permission.py
    - backend/alembic/versions/q4r5s6t7u8v9_add_permission_system.py
  modified:
    - backend/app/models/__init__.py

key-decisions:
  - "FK user_org_access_id (not user_id+org_id pair) per D-08 — UserOrgAccess already enforces uniqueness"
  - "publication.create NOT seeded into role_permissions — per-user override via can_publish migration"
  - "admin.billing seeded for superadmin + org_admin per PLAN.md matrix (not RESEARCH matrix discrepancy)"
  - "user.manage seeded for superadmin, account_owner, admin only (not manager/employee)"
  - "__init__.py uses absolute imports (from app.models.X) consistent with rest of file"

patterns-established:
  - "Permission models follow user_org_access.py style: Column, ForeignKey, UniqueConstraint, relationship"
  - "Migration seed uses connection.execute(sa.text(...)) with named params dict per-row for idempotency"

requirements-completed: [D-01, D-02, D-05, D-06, D-07, D-08]

# Metrics
duration: 2min
completed: 2026-04-23
---

# Phase 17 Plan 01: Permission System Foundation Summary

**Four permission tables (permission_tabs/actions/role_permissions/user_org_permission_overrides) with idempotent alembic migration seeding 23 tab + 7 action rows from hardcoded ADMIN/MANAGER/ALL_ROLES matrix, plus can_publish→publication.create data migration**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-23T09:40:57Z
- **Completed:** 2026-04-23T09:43:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Four SQLAlchemy models with correct UniqueConstraints and ForeignKey to user_org_access.id
- Alembic migration q4r5s6t7u8v9 with Step A (4 tables) + Step B (23 tabs) + Step C (7 actions) + Step D (role matrix) + Step E (can_publish migration)
- All 4 INSERT steps use ON CONFLICT DO NOTHING — running upgrade twice is safe
- Models registered in __init__.py following existing absolute import convention

## Task Commits

Each task was committed atomically:

1. **Task 1: Create permission models + __init__ registration** - `9957465` (feat)
2. **Task 2: Alembic migration — schema + seed + can_publish data migration** - `3a81a09` (feat)

## Files Created/Modified
- `backend/app/models/permission.py` - Four SQLAlchemy models: PermissionTab, PermissionAction, RolePermission, UserOrgPermissionOverride
- `backend/alembic/versions/q4r5s6t7u8v9_add_permission_system.py` - Idempotent migration: 4 tables + seed + can_publish migration
- `backend/app/models/__init__.py` - Added absolute import for all four models

## Decisions Made
- FK on UserOrgPermissionOverride uses `user_org_access_id` (single FK to user_org_access.id) rather than `(user_id, org_id)` pair — UserOrgAccess already has uq_user_org constraint, so this is cleaner per D-08
- `publication.create` is NOT seeded into role_permissions. It is only created as per-user UserOrgPermissionOverride from can_publish=True migration (Step E). This matches the plan spec.
- `admin.billing` grants access to `{'superadmin', 'org_admin'}` per PLAN.md spec (RESEARCH matrix showed only superadmin but PLAN.md is authoritative)
- Absolute import style (`from app.models.permission import`) used in __init__.py to match all other existing imports in that file

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Python `open()` on Windows defaulted to cp1251 encoding (Cyrillic in SQL strings). Verified via `open(..., encoding='utf-8')` — syntax check passed.

## User Setup Required
None - no external service configuration required. Migration runs automatically on next autodeploy push.

## Next Phase Readiness
- Foundation ready for Plan 17-02 (test scaffolds: pytest tests querying role_permissions)
- Foundation ready for Plan 17-03 (require_tab() factory can query role_permissions via ORM)
- All 4 tables will be created when alembic runs `q4r5s6t7u8v9` on the server after autodeploy

## Known Stubs

None — no stub values or placeholder data. Migration seeds real permission data from existing hardcoded constants.

---
*Phase: 17-permission-system-override*
*Completed: 2026-04-23*
