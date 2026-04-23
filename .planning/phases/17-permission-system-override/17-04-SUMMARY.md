---
phase: 17-permission-system-override
plan: "04"
subsystem: auth
tags: [fastapi, permissions, require_tab, require_action, role-based-access, routers]

# Dependency graph
requires:
  - phase: 17-03
    provides: require_tab, require_action Depends factories in app.auth.permissions
  - phase: 17-01
    provides: role_permissions seed data ensuring zero regression
provides:
  - All 78+ require_role() call-sites in 21 router files replaced with require_tab/require_action
  - publications.py POST /purchases/{id} guarded by require_action('publication.create') (D-06)
affects:
  - 17-05-PLAN (users.py GET / stays require_role(*ALL_ROLES) — 17-05 will handle superadmin filter there)
  - 17-06-PLAN (frontend now expects tabs/actions from /users/me for gating all API-guarded routes)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Mechanical require_role → require_tab/require_action substitution using sed per cluster"
    - "Preserve require_role import line even after migration (other usages may exist inline)"
    - "Only 1 require_role Depends() intentionally remains: users.py GET / (ALL_ROLES authenticated gate)"

key-files:
  created: []
  modified:
    - backend/app/routers/departments.py
    - backend/app/routers/hierarchy.py
    - backend/app/routers/user_hierarchy.py
    - backend/app/routers/settings.py
    - backend/app/routers/system_incidents.py
    - backend/app/routers/events.py
    - backend/app/routers/contractors.py
    - backend/app/routers/contracts.py
    - backend/app/routers/commercial_requests.py
    - backend/app/routers/suppliers.py
    - backend/app/routers/purchases.py
    - backend/app/routers/purchase_transitions.py
    - backend/app/routers/purchase_events.py
    - backend/app/routers/purchase_items_import.py
    - backend/app/routers/payments.py
    - backend/app/routers/subsidies.py
    - backend/app/routers/feo_categories.py
    - backend/app/routers/feo_planned_items.py
    - backend/app/routers/products.py
    - backend/app/routers/users.py
    - backend/app/routers/wishes.py
    - backend/app/routers/publications.py

key-decisions:
  - "purchases.py bulk_delete and delete_purchase both mapped to require_tab('purchases') — no separate delete action seeded for purchases"
  - "subsidies.py update_subsidy (ADMIN write) → require_action('subsidy.edit'); delete_subsidy (superadmin/account_owner) → require_tab('subsidies')"
  - "publications.py can_publish inline check was already absent; added require_action('publication.create') declaratively on POST endpoint"
  - "users.py GET / stays require_role(*ALL_ROLES) — Plan 17-05 handles superadmin visibility filter there"
  - "events.py reuses admin.settings tab key — no dedicated admin.events seeded in v1"

patterns-established:
  - "require_tab(tab_key) replaces require_role(*ADMIN_ROLES) / require_role(*MANAGER_ROLES) / require_role(*ALL_ROLES) on list/CRUD endpoints"
  - "require_action(action_key) replaces require_role on high-risk single operations (delete contract, register payment, publish, manage users, transition purchase, edit subsidy)"

requirements-completed: [D-01, D-06]

# Metrics
duration: 30min
completed: 2026-04-23
---

# Phase 17 Plan 04: Router Call-site Migration Summary

**78+ require_role() call-sites across 22 router files migrated to require_tab/require_action per database-backed permission matrix; publications.py declarative require_action('publication.create') guard added (D-06)**

## Performance

- **Duration:** 30 min
- **Started:** 2026-04-23T10:30:00Z
- **Completed:** 2026-04-23T11:00:00Z
- **Tasks:** 4
- **Files modified:** 22

## Accomplishments

- Task 1 (21 sites): departments (10), hierarchy (5), user_hierarchy (2), settings (3), system_incidents (3), events (3) — all → require_tab('staff'/'admin.settings'/'system_incidents')
- Task 2 (24 sites): contractors (11), contracts (7+1 action), commercial_requests (5), suppliers (5) — require_tab + 1 require_action('contract.delete')
- Task 3 (~33 sites): purchases (2), purchase_transitions (1 action), purchase_events (2), purchase_items_import (3), payments (2+1 action), subsidies (8+2 action), feo_categories (11), feo_planned_items (4)
- Task 4 (9 sites): products (1), users (6), wishes (1), publications (1 action) — plus D-06 migration complete

## Task Commits

Each task was committed atomically:

1. **Task 1: staff/admin-settings/incidents cluster** - `1ab78d4` (feat)
2. **Task 2: procurement counterparty cluster** - `9382367` (feat)
3. **Task 3: financial cluster** - `0e1db68` (feat)
4. **Task 4: secondary cluster + publications D-06** - `cbe620b` (feat)

## Files Created/Modified

- `backend/app/routers/departments.py` - 10 require_role → require_tab('staff')
- `backend/app/routers/hierarchy.py` - 5 → require_tab('staff')
- `backend/app/routers/user_hierarchy.py` - 2 → require_tab('staff')
- `backend/app/routers/settings.py` - 3 → require_tab('admin.settings')
- `backend/app/routers/system_incidents.py` - 3 → require_tab('system_incidents')
- `backend/app/routers/events.py` - 3 → require_tab('admin.settings')
- `backend/app/routers/contractors.py` - 11 → require_tab('contractors')
- `backend/app/routers/contracts.py` - 7 → require_tab('contracts'), 1 → require_action('contract.delete')
- `backend/app/routers/commercial_requests.py` - 5 → require_tab('commercial_requests')
- `backend/app/routers/suppliers.py` - 5 → require_tab('contractors')
- `backend/app/routers/purchases.py` - 2 → require_tab('purchases')
- `backend/app/routers/purchase_transitions.py` - 1 → require_action('purchase.transition_status')
- `backend/app/routers/purchase_events.py` - 2 → require_tab('purchases')
- `backend/app/routers/purchase_items_import.py` - 3 → require_tab('purchases')
- `backend/app/routers/payments.py` - 2 → require_tab('contracts'), 1 → require_action('payment.register')
- `backend/app/routers/subsidies.py` - 8 → require_tab('subsidies'), 2 → require_action('subsidy.edit')
- `backend/app/routers/feo_categories.py` - 11 → require_tab('feo_categories')
- `backend/app/routers/feo_planned_items.py` - 4 → require_tab('feo_categories')
- `backend/app/routers/products.py` - 1 → require_tab('products')
- `backend/app/routers/users.py` - 6 → require_action('user.manage'); GET / stays require_role(*ALL_ROLES)
- `backend/app/routers/wishes.py` - 1 → require_tab('wishes')
- `backend/app/routers/publications.py` - POST /purchases/{id} → require_action('publication.create') (D-06)

## Decisions Made

- purchases.py bulk_delete and delete_purchase both mapped to `require_tab('purchases')` — no separate delete action seeded for purchases in this phase
- subsidies.py `update_subsidy` (ADMIN write) → `require_action('subsidy.edit')`; `delete_subsidy` (superadmin/account_owner) → `require_tab('subsidies')` (delete is org-owner scoped)
- publications.py inline `can_publish` check was already absent (removed in earlier feedback fix); added `require_action('publication.create')` declaratively on POST endpoint per D-06
- users.py GET `/users/` stays `require_role(*ALL_ROLES)` — authenticated access only, Plan 17-05 handles superadmin filter here
- events.py reuses `admin.settings` tab key — no dedicated `admin.events` seeded in v1 matix

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] publications.py had no can_publish inline check to remove**
- **Found during:** Task 4 (publications.py Step B)
- **Issue:** The plan said to remove `if not current_user.can_publish` inline checks, but grep returned 0 matches — the check was already removed in a prior feedback fix (2026-04-15 Golichkov-3 session)
- **Fix:** Skipped removal step; proceeded directly to adding `require_action('publication.create')` declaratively on the POST endpoint — which is the actual D-06 goal
- **Files modified:** backend/app/routers/publications.py
- **Committed in:** cbe620b (Task 4 commit)

---

**Total deviations:** 1 (plan step was no-op, handled gracefully)
**Impact on plan:** Zero scope change. D-06 goal achieved as specified.

## Issues Encountered

- Plan line numbers (612, 634 in purchases.py) slightly mismatched actual code due to intervening edits. Resolved by using semantic intent (DELETE endpoints) rather than raw line numbers.

## User Setup Required

None - no external service configuration required. Changes take effect on next autodeploy push.

## Next Phase Readiness

- All API endpoints now gated by database-backed permission matrix via `require_tab`/`require_action`
- Only `users.py GET /` remains on `require_role(*ALL_ROLES)` — this is intentional for 17-05
- Plan 17-05 (self-lockout + superadmin visibility in users.py/task_visibility.py/tasks.py) can proceed immediately
- Plan 17-06 (frontend Pinia store consuming /users/me permissions) can also proceed immediately

## Known Stubs

None — this plan performs mechanical substitution only; no data is stubbed or hardcoded.

---
*Phase: 17-permission-system-override*
*Completed: 2026-04-23*

## Self-Check: PASSED

- All 22 router files exist on disk: CONFIRMED
- All 4 task commits exist in git: 1ab78d4, 9382367, 0e1db68, cbe620b CONFIRMED
- Only 1 `Depends(require_role` call remains (users.py GET / — intentional): CONFIRMED
- publications.py `require_action('publication.create')` guard present: CONFIRMED
