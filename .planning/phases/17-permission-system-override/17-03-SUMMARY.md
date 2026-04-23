---
phase: 17-permission-system-override
plan: "03"
subsystem: auth
tags: [fastapi, sqlalchemy, permissions, role-based-access, pydantic, async]

# Dependency graph
requires:
  - phase: 17-01
    provides: RolePermission, UserOrgPermissionOverride, PermissionTab, PermissionAction SQLAlchemy models
  - phase: 17-02
    provides: test_require_tab.py, test_users_me_permissions.py test scaffolding (RED state)
provides:
  - backend/app/auth/permissions.py with get_effective_tabs, get_effective_actions, require_tab, require_action
  - PermissionsOut Pydantic schema in schemas.py
  - UserOut.permissions: Optional[PermissionsOut] field
  - GET /api/users/me?org_id=N returns permissions.tabs + permissions.actions
affects:
  - 17-04-PLAN (call-site migration: require_role → require_tab/require_action in 78+ routers)
  - 17-05-PLAN (self-lockout + superadmin visibility use require_tab)
  - 17-06-PLAN (frontend Pinia store consumes /users/me permissions field)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Boolean-flip permission resolution: base from role_permissions + per-org overrides via user_org_access_id FK"
    - "Superadmin bypass (D-05.3): early return before any DB query"
    - "FastAPI Depends factory pattern for require_tab/require_action — mirrors existing require_role"
    - "Split effective key set back to tabs vs actions by intersecting with PermissionTab/PermissionAction dictionaries"

key-files:
  created:
    - backend/app/auth/permissions.py
  modified:
    - backend/app/schemas/schemas.py
    - backend/app/routers/users.py

key-decisions:
  - "require_tab/require_action import directly from app.auth.permissions at call-sites (no jwt.py re-export needed)"
  - "get_effective_tabs and get_effective_actions both call same _get_effective() internally — tabs/actions share same key namespace"
  - "Split effective set into tabs vs actions using PermissionTab/PermissionAction dictionary tables at /me endpoint (not in _get_effective)"
  - "superadmin at /me endpoint returns ALL tab+action keys from dictionary tables (sorted) instead of DB query bypass"

patterns-established:
  - "Permission check factories mirror require_role() pattern: return async checker with Depends(get_current_user)+Depends(get_db)"
  - "Per-org JOIN pattern: UserOrgPermissionOverride JOIN UserOrgAccess WHERE user_id=... AND org_id=..."

requirements-completed: [D-01, D-02, D-05, D-06, D-08]

# Metrics
duration: 10min
completed: 2026-04-23
---

# Phase 17 Plan 03: Permission Resolution Service Summary

**Permission resolution service with boolean-flip override mechanics, superadmin bypass, require_tab/require_action Depends factories, and /users/me extended to return effective tabs+actions per org**

## Performance

- **Duration:** 10 min
- **Started:** 2026-04-23T10:00:00Z
- **Completed:** 2026-04-23T10:10:00Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- New `backend/app/auth/permissions.py` with `_get_effective()` boolean-flip resolver, `get_effective_tabs`, `get_effective_actions`, `require_tab`, `require_action`
- `PermissionsOut` Pydantic schema added to schemas.py; `UserOut.permissions: Optional[PermissionsOut]` field added (backward-compatible, defaults to None)
- `GET /api/users/me` accepts `?org_id=N` query param and returns `permissions.tabs` + `permissions.actions` lists resolved for that org

## Task Commits

Each task was committed atomically:

1. **Task 1: Create permission resolution service + require_tab/require_action factories** - `1f14dca` (feat)
2. **Task 2: Extend UserOut schema + /api/users/me endpoint with permissions field** - `6a69ec3` (feat)

## Files Created/Modified

- `backend/app/auth/permissions.py` - Permission resolution service: `_get_effective`, `get_effective_tabs`, `get_effective_actions`, `require_tab`, `require_action` with superadmin bypass
- `backend/app/schemas/schemas.py` - Added `PermissionsOut(tabs, actions)` model; added `permissions: Optional[PermissionsOut]` to `UserOut`
- `backend/app/routers/users.py` - Extended `/me` with `org_id` Query param; resolves effective tabs+actions; superadmin returns all keys from dictionary tables

## Decisions Made

- `require_tab`/`require_action` import directly from `app.auth.permissions` at call-sites — no re-export through `jwt.py` needed (plan revised this mid-spec, kept simpler approach)
- Both `get_effective_tabs` and `get_effective_actions` are thin aliases calling the same `_get_effective()` — tabs and actions share the same flat key namespace in `role_permissions`
- The `/me` endpoint splits the unified effective key set into tabs vs actions by intersecting with `PermissionTab.tab_key` / `PermissionAction.action_key` dictionary rows
- Superadmin at `/me` returns ALL tab+action keys by querying dictionary tables (not a bypass returning empty) — ensures UI can show all controls for superadmin

## Deviations from Plan

None - plan executed exactly as written. The plan's own "Revised instruction" (leave jwt.py unchanged) was already incorporated into the action spec.

## Issues Encountered

None - all imports aligned with existing codebase patterns, no missing dependencies.

## User Setup Required

None - no external service configuration required. All code changes take effect on next autodeploy push.

## Next Phase Readiness

- `require_tab(tab_key)` and `require_action(action_key)` are ready for call-site migration in Plan 17-04 (78+ `require_role` call-sites in routers)
- `/api/users/me?org_id=N` now returns `permissions.tabs` and `permissions.actions` — frontend Pinia store (Plan 17-06) can consume this
- Tests `test_require_tab.py` and `test_users_me_permissions.py` should turn GREEN once Plan 17-04 migrates at least one router to `require_tab` (e.g., `/api/hierarchy/` to `require_tab('staff')`)

## Known Stubs

None — no placeholder or hardcoded values. All data flows from live `role_permissions` + `user_org_permission_overrides` tables seeded by Plan 17-01 migration.

---
*Phase: 17-permission-system-override*
*Completed: 2026-04-23*
