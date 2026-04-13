---
phase: 07-roles-wishes-workflow
plan: "03"
subsystem: ui
tags: [vue3, vuetify3, wishes, roles, navigation, employee-guard]

# Dependency graph
requires:
  - phase: 07-02
    provides: POST/PUT/DELETE /api/wishes endpoints, approve/reject/convert transitions
  - phase: 07-01
    provides: Wish SQLAlchemy model and GET /api/wishes endpoint

provides:
  - WishesView.vue with role-based tabs (employee: own wishes, manager/admin: all wishes)
  - /wishes route registered in Vue Router
  - Employee guard updated to allow /wishes
  - AppBar navigation entry for all roles
  - Advance reports navigation fixed to ALL_ROLES per D-09

affects: [07-roles-wishes-workflow, navigation, employee-access]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Role-split tabs: isManagerOrAdmin computed drives v-tabs visibility"
    - "apiFetch('/wishes?mine_only=true') for employee own-wishes, apiFetch('/wishes?status=X') for manager view"
    - "Status chip color map Record<string, string> for draft/submitted/approved/rejected/converted"

key-files:
  created:
    - frontend/src/views/WishesView.vue
  modified:
    - frontend/src/router/index.ts
    - frontend/src/components/AppBar.vue

key-decisions:
  - "Employee tab shown unconditionally, manager/admin see v-tabs with two tabs"
  - "allFilter defaults to 'submitted' so manager sees actionable items immediately"
  - "Convert dialog pre-fills approved_quantity/price from wish data for convenience"
  - "Advance reports changed from MANAGER_ROLES to ALL_ROLES (D-09 requirement)"

patterns-established:
  - "Role check via localStorage user_role + computed isManagerOrAdmin/isAdmin"
  - "FAB fixed-position button for create action (position:fixed;bottom:32px;right:32px)"

requirements-completed: [WISHES-06, WISHES-07, ROLES-01, ROLES-02, ROLES-04, ROLES-05]

# Metrics
duration: 25min
completed: 2026-04-05
---

# Phase 07 Plan 03: Wishes Frontend Summary

**WishesView.vue with role-split tabs, /wishes route, employee guard, and AppBar navigation — full wish lifecycle UI (create, submit, approve, reject, convert)**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-05T00:00:00Z
- **Completed:** 2026-04-05
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- WishesView.vue (685 lines): employee sees own wishes with create/edit/submit/delete actions; manager/admin see all wishes with approve/reject/convert actions
- Status chips with correct colors: draft=grey, submitted=blue, approved=green, rejected=red, converted=purple
- Convert dialog with approved_quantity/approved_price inputs pre-filled from wish data, optional subsidy dropdown
- /wishes route with lazy import, employee guard updated, EMPLOYEE_ALLOWED array updated
- AppBar menuItems and allNavShortcuts both include Заявки with ALL_ROLES
- Авансовые отчёты changed from MANAGER_ROLES to ALL_ROLES per D-09

## Task Commits

1. **Task 1: Create WishesView.vue with role-based tabs** - `7a62953` (feat)
2. **Task 2: Add /wishes route and update employee guard + AppBar navigation** - `42ad7ce` (feat)

**Plan metadata:** pending

## Files Created/Modified

- `frontend/src/views/WishesView.vue` - Role-split wishes view: employee tab + manager/admin tab with full lifecycle
- `frontend/src/router/index.ts` - /wishes route, employee guard path check, EMPLOYEE_ALLOWED update
- `frontend/src/components/AppBar.vue` - Заявки nav item (menuItems + allNavShortcuts), advance reports ALL_ROLES fix

## Decisions Made

- Employee tab shows unconditionally (no v-tabs bar), manager/admin get two tabs — simpler UX for employees
- Manager filter defaults to "submitted" to show immediately actionable wishes, not all wishes
- Convert dialog pre-fills from wish data — reduces manual entry for org_admin

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The `apiFetch` helper prepends `/api` so calls use paths like `/wishes` (not `/api/wishes`), consistent with all other views in the codebase.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Wishes full lifecycle is now complete end-to-end: backend (07-01, 07-02) + frontend (07-03)
- Employee can navigate to /wishes from sidebar, create/submit wishes
- Manager can approve/reject submitted wishes
- org_admin can convert approved wishes to purchases via inline Purchase creation

---
*Phase: 07-roles-wishes-workflow*
*Completed: 2026-04-05*
