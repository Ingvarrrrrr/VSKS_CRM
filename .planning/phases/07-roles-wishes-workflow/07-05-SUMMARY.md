---
phase: 07-roles-wishes-workflow
plan: 05
subsystem: auth
tags: [fastapi, role-based-access-control, require_role, jwt, permissions]

# Dependency graph
requires:
  - phase: 07-01
    provides: Wish model and router; role constants MANAGER_ROLES, ADMIN_ROLES defined in jwt.py
provides:
  - Server-side HTTP 403 enforcement for employee-forbidden endpoints
  - require_role(*MANAGER_ROLES) on all subsidies, contracts, payments endpoints
  - require_role(*ADMIN_ROLES) on all feo_categories and users list endpoint
  - Previously unauthenticated feo_categories endpoints (create, update, delete, move, import, export) now gated
affects: [08-roles-wishes-workflow, testing, e2e]

# Tech tracking
tech-stack:
  added: []
  patterns: [require_role dependency injection replacing inline role checks, bare get_current_user removed from all admin endpoints]

key-files:
  created: []
  modified:
    - backend/app/routers/subsidies.py
    - backend/app/routers/contracts.py
    - backend/app/routers/payments.py
    - backend/app/routers/feo_categories.py
    - backend/app/routers/users.py

key-decisions:
  - "update_subsidy inline ADMIN_ROLES check replaced with require_role(*ADMIN_ROLES) dependency — cleaner, consistent pattern"
  - "delete_subsidy inline OWNER_ROLES check replaced with require_role('superadmin', 'account_owner') — keeps OWNER semantics without importing OWNER_ROLES constant"
  - "feo_categories endpoints that had NO auth (create, update, delete, move, import, export, purchase-totals) now gated with ADMIN_ROLES — these were previously fully open (Rule 2 auto-fix: missing critical auth)"
  - "contracts import/preview endpoints upgraded from get_current_user to MANAGER_ROLES — file import is a privileged operation"
  - "users.py get_me, get_my_signature, upload_signature remain get_current_user — personal profile is self-service for all roles"

patterns-established:
  - "Use require_role(*ROLE_SET) as FastAPI Depends — returns current_user, variable name unchanged"
  - "Never use bare get_current_user on endpoints that should be restricted; use require_role even if just for auth presence"
  - "Inline role checks (if current_user.role not in X: raise HTTPException(403)) replaced by require_role dependency for uniformity"

requirements-completed: [ROLES-03]

# Metrics
duration: 25min
completed: 2026-04-05
---

# Phase 07 Plan 05: Role Gate Enforcement Summary

**HTTP 403 server-side enforcement via require_role(*MANAGER_ROLES/ADMIN_ROLES) on subsidies, contracts, payments, feo_categories, and users list — employees can no longer reach these endpoints with a valid JWT**

## Performance

- **Duration:** 25 min
- **Started:** 2026-04-05T00:00:00Z
- **Completed:** 2026-04-05T00:25:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- All subsidies endpoints require MANAGER_ROLES minimum (employees get HTTP 403)
- All contracts list/create/update/import require MANAGER_ROLES; delete/merge retain ADMIN_ROLES
- payments list_payments upgraded from bare get_current_user to require_role(*MANAGER_ROLES)
- All feo_categories endpoints now require ADMIN_ROLES — including previously unauthenticated ones
- users list_users upgraded from get_current_user to require_role(*ADMIN_ROLES)
- Inline role checks (if current_user.role not in X) consolidated into require_role dependency pattern

## Task Commits

Each task was committed atomically:

1. **Task 1: Add require_role guards to subsidies, contracts, payments, feo_categories, users** - `a166a89` (feat)
2. **Task 2: Verify role gating** - verification only, no code changes

## Files Created/Modified
- `backend/app/routers/subsidies.py` - All endpoints now use require_role; MANAGER_ROLES/ADMIN_ROLES imported; inline checks removed
- `backend/app/routers/contracts.py` - list/create/update/import use MANAGER_ROLES; delete/merge unchanged
- `backend/app/routers/payments.py` - list_payments upgraded to MANAGER_ROLES; import added
- `backend/app/routers/feo_categories.py` - All endpoints gated with ADMIN_ROLES; 7 previously unauthenticated endpoints now secured
- `backend/app/routers/users.py` - list_users upgraded to ADMIN_ROLES; personal profile endpoints unchanged

## Decisions Made
- Inline role checks replaced with require_role dependency for consistency — same behavior, cleaner code
- feo_categories endpoints with NO auth were upgraded (Rule 2: missing critical functionality)
- OWNER_ROLES constant not imported in subsidies.py delete endpoint; used literal tuple instead

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added require_role to 7 feo_categories endpoints that had NO authentication**
- **Found during:** Task 1
- **Issue:** feo_categories.py had create_category, update_category, delete_category, move_category, import_feo_from_excel, export_feo_to_excel, and get_purchase_totals with no auth dependency at all — any HTTP client could call them without a token
- **Fix:** Added `_=Depends(require_role(*ADMIN_ROLES))` to all 7 endpoints
- **Files modified:** backend/app/routers/feo_categories.py
- **Verification:** grep confirms zero bare Depends(get_current_user) in feo_categories.py
- **Committed in:** a166a89 (Task 1 commit)

**2. [Rule 2 - Missing Critical] Upgraded contracts import endpoints from get_current_user to MANAGER_ROLES**
- **Found during:** Task 1
- **Issue:** /contracts/import/preview and /contracts/import/mapped used bare get_current_user — employees could trigger bulk import operations
- **Fix:** Changed to require_role(*MANAGER_ROLES)
- **Files modified:** backend/app/routers/contracts.py
- **Verification:** grep confirms no bare get_current_user on import endpoints
- **Committed in:** a166a89 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 2: missing critical auth)
**Impact on plan:** Both auto-fixes closed unauthenticated/under-authenticated API surface. No scope creep — all changes are role-gating.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. Changes take effect after Docker image rebuild.

## Next Phase Readiness
- ROLES-03 fully satisfied: employee JWT returns HTTP 403 on all forbidden endpoints
- Ready to implement Wishes CRUD (07-02) and "Мои заявки" views
- No blockers

---
*Phase: 07-roles-wishes-workflow*
*Completed: 2026-04-05*
