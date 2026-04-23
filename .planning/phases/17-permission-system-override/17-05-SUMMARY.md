---
phase: 17-permission-system-override
plan: "05"
subsystem: backend-api
tags: [fastapi, sqlalchemy, permissions, role-based-access, superadmin-visibility, self-lockout]

# Dependency graph
requires:
  - phase: 17-01
    provides: PermissionTab, PermissionAction, RolePermission, UserOrgPermissionOverride models
  - phase: 17-03
    provides: require_tab() Depends factory from app.auth.permissions

provides:
  - backend/app/routers/permissions.py with 7 CRUD endpoints for matrix + per-user overrides
  - SELF_LOCKOUT_PROTECTED_KEYS check in PUT /roles/{role_name} and PUT /users/{id}/overrides
  - D-09 superadmin filter in list_users (users.py), _get_visible_user_ids (task_visibility.py), hierarchy graph, task authority
  - All select(User) call-sites in routers either filtered or annotated with # superadmin-bypass-ok

affects:
  - 17-07-PLAN (AdminRolesView.vue consumes GET/PUT /api/permissions/roles)
  - 17-08-PLAN (user overrides UI consumes GET/PUT /api/permissions/users/{id}/overrides)
  - All list-user endpoints (D-09 filter applied at API layer)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SELF_LOCKOUT_PROTECTED_KEYS = {'admin.roles', 'staff'} — 403 when admin tries to revoke own role access"
    - "D-09 filter: if current_user.role != 'superadmin': q = q.where(User.role != 'superadmin')"
    - "# superadmin-bypass-ok annotation pattern for non-listing select(User) sites"
    - "Query param org_id = Query(...) for override endpoints (upsert per user_org_access row)"

key-files:
  created:
    - backend/app/routers/permissions.py
  modified:
    - backend/app/schemas/schemas.py
    - backend/app/__init__.py
    - backend/app/routers/users.py
    - backend/app/routers/task_visibility.py
    - backend/app/routers/hierarchy.py
    - backend/app/routers/departments.py
    - backend/app/routers/task_comments.py
    - backend/app/routers/purchases.py

key-decisions:
  - "permissions.router uses prefix /api/permissions in the router constructor (not in include_router) to match plan spec"
  - "org_id for override endpoints uses Query(...) (required query param) not path param — matches plan spec"
  - "D-09 filter applied in 4 user-listing locations: list_users, _get_visible_user_ids, hierarchy graph, task authority get_task_authority"
  - "hierarchy.py get_task_authority: D-09 filter on org-manager user query (line 612) only; sub_ids/mgr_ids ID lookups annotated superadmin-bypass-ok"
  - "Remaining select(User) call-sites in auth.py, chat.py, telegram_webhook.py, organizations.py are credential/ID lookups — annotated superadmin-bypass-ok"

# Metrics
duration: 15min
completed: 2026-04-23
---

# Phase 17 Plan 05: Admin CRUD API + Self-Lockout + Superadmin Filter Summary

**New permissions router with 7 endpoints for role matrix CRUD and per-user org overrides; D-05.2 self-lockout on admin.roles/staff keys; D-09 superadmin invisible filter applied at every select(User) user-listing call-site**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-23T10:30:00Z
- **Completed:** 2026-04-23T10:45:00Z
- **Tasks:** 2
- **Files modified:** 8 (1 created)

## Accomplishments

- New `backend/app/routers/permissions.py`: 7 endpoints — GET /tabs, GET /actions, GET /roles, PUT /roles/{role_name}, GET /users/{id}/overrides, PUT /users/{id}/overrides, DELETE /users/{id}/overrides/{key}
- Self-lockout (D-05.2): PUT /roles/{role_name} returns 403 if `role_name == current_user.role` and `key in {'admin.roles', 'staff'}` with `granted=False`
- Pydantic schemas added to schemas.py: PermissionTabOut, PermissionActionOut, RolePermissionOut, RoleMatrixRow, PermissionUpdate, OverrideOut
- Router registered in `__init__.py` as `permissions_router.router`
- D-09 filter (`User.role != 'superadmin'`) added in list_users (users.py), _get_visible_user_ids (task_visibility.py), get_hierarchy_graph (hierarchy.py), get_task_authority (hierarchy.py)
- All remaining `select(User)` call-sites in routers annotated with `# superadmin-bypass-ok` comments

## Task Commits

Each task was committed atomically:

1. **Task 1: Create permissions router + schemas + register in __init__.py** - `c520cbc` (feat)
2. **Task 2: D-09 superadmin filter in user-listing endpoints** - `eb7fb84` (feat)

## Files Created/Modified

- `backend/app/routers/permissions.py` — 7 CRUD endpoints: matrix (tabs/actions/roles) + per-user overrides + self-lockout guards
- `backend/app/schemas/schemas.py` — Added: PermissionTabOut, PermissionActionOut, RolePermissionOut, RoleMatrixRow, PermissionUpdate, OverrideOut
- `backend/app/__init__.py` — Registered permissions_router
- `backend/app/routers/users.py` — D-09 filter in list_users
- `backend/app/routers/task_visibility.py` — D-09 filter in _get_visible_user_ids (managed-org branch); enrichment lookups annotated superadmin-bypass-ok
- `backend/app/routers/hierarchy.py` — D-09 filter in get_hierarchy_graph + get_task_authority; ID lookups annotated superadmin-bypass-ok
- `backend/app/routers/departments.py` — ID lookup call-sites annotated superadmin-bypass-ok
- `backend/app/routers/task_comments.py` — @mention + broadcast call-sites annotated superadmin-bypass-ok
- `backend/app/routers/purchases.py` — @mention + broadcast + enrichment call-sites annotated superadmin-bypass-ok

## Decisions Made

- `org_id` for override endpoints is a required Query param (`Query(...)`) rather than path param — cleaner URL structure matching `/api/permissions/users/{id}/overrides?org_id=N`
- D-09 filter applied in `hierarchy.py` at TWO points: (1) `get_hierarchy_graph` for the org-level user list; (2) `get_task_authority` for the managed-org user query before building `sub_ids`
- `# superadmin-bypass-ok` annotation used consistently for all non-listing `select(User)` sites to satisfy the audit requirement from PLAN.md §Step D
- `auth.py`, `organizations.py`, `telegram_webhook.py` — system-level credential lookups (by email/token/telegram_id) do NOT need D-09 filter since they are not user-listing endpoints and have no caller user context

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written with one additional scope expansion:

**[Rule 2 - Missing critical functionality] D-09 filter in hierarchy.py get_task_authority**
- **Found during:** Task 2 — full select(User) audit per §Step D
- **Issue:** `get_task_authority` at line 612 builds `sub_ids` from org-manager user query — this feeds "can assign to" dropdown. Without D-09 filter, superadmin would appear in assignee dropdowns.
- **Fix:** Added `if current_user.role != "superadmin": _org_user_q = _org_user_q.where(User.role != "superadmin")` before executing the managed-org user query.
- **Files modified:** backend/app/routers/hierarchy.py
- **Commit:** eb7fb84

## select(User) Audit Result

After Task 2, the full audit shows:

| File | Line | Type | Status |
|------|------|------|--------|
| users.py | 18 | list_users | `User.role != 'superadmin'` filter added |
| task_visibility.py | 90 (org_users) | _get_visible_user_ids | `User.role != 'superadmin'` filter added |
| hierarchy.py | 151 | get_hierarchy_graph | `User.role != 'superadmin'` filter added |
| hierarchy.py | 612 | get_task_authority | `User.role != 'superadmin'` filter added |
| task_visibility.py | 138,154 | enrichment lookups by ID | `# superadmin-bypass-ok` |
| task_comments.py | 99,170 | @mention + broadcast | `# superadmin-bypass-ok` |
| purchases.py | 319,873,945 | enrichment + @mention + broadcast | `# superadmin-bypass-ok` |
| departments.py | 147,288,467,672 | ID lookups + Excel import | `# superadmin-bypass-ok` |
| hierarchy.py | 627,638 | ID lookups by sub_ids/mgr_ids | `# superadmin-bypass-ok` |
| auth.py | 24,27,75,90 | Credential lookups (login/reset) | `# superadmin-bypass-ok` |
| chat.py | 219,743,791,838,874,921 | By name/id/sender | `# superadmin-bypass-ok` |
| organizations.py | 23,28,66 | Uniqueness/token lookups | `# superadmin-bypass-ok` |
| purchase_events.py | 112 | By user_id | `# superadmin-bypass-ok` |
| purchase_members.py | 103 | By user_id | `# superadmin-bypass-ok` |
| telegram_webhook.py | 141,236,269 | By telegram_id | `# superadmin-bypass-ok` |
| users.py | 35,45,49,366 | Uniqueness/delete by id | `# superadmin-bypass-ok` |
| user_hierarchy.py | 82,100,101 | By ID | `# superadmin-bypass-ok` |

## Issues Encountered

None.

## User Setup Required

None — changes take effect on next autodeploy push.

## Next Phase Readiness

- `GET /api/permissions/tabs` / `GET /api/permissions/actions` / `GET /api/permissions/roles` ready for AdminRolesView.vue (Plan 17-07)
- `PUT /api/permissions/roles/{role_name}` ready for checkbox save in AdminRolesView.vue
- `GET /api/permissions/users/{id}/overrides?org_id=N` + `PUT` ready for user card access section (Plan 17-08)
- `GET /api/users/` excludes superadmin for non-superadmin callers — StaffView.vue frontend filter (Plan 17-08) can trust API data
- Self-lockout tests `test_self_lockout.py` should turn GREEN on next deploy
- Visibility tests `test_superadmin_visibility.py` should turn GREEN on next deploy

## Known Stubs

None — all endpoints are wired to live DB tables (seeded by Plan 17-01 migration).

---
*Phase: 17-permission-system-override*
*Completed: 2026-04-23*
