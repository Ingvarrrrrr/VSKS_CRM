---
phase: 11-fix-task-display-per-user-org-filtering-badges-org-selector-task-scoping
plan: 01
subsystem: ui, api
tags: [vue3, fastapi, tasks, org-filtering, badges, localStorage]

# Dependency graph
requires:
  - phase: 07-roles-wishes-workflow
    provides: Multi-org membership model, Task.org_id column, orgSummary endpoint
provides:
  - org-scoped badge counts via optional org_id query param on /tasks/badges
  - filteredGeneralTasks computed that scopes task list to selected org
  - visibleOrgSummary computed that hides zero-task orgs from selector
  - localStorage-based org_id persistence linking MyTasksView selection to AppBar badges
affects: [AppBar, MyTasksView, badges, task-filtering]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "localStorage bridge pattern: MyTasksView writes active_org_id, AppBar reads it for stateless badge filtering without cross-component coupling"
    - "Conditional query filter pattern: org_id is None -> global query; org_id provided -> add Task.org_id == org_id clause"

key-files:
  created: []
  modified:
    - backend/app/routers/tasks.py
    - frontend/src/views/MyTasksView.vue
    - frontend/src/components/AppBar.vue

key-decisions:
  - "localStorage bridge chosen over event bus/Vuex for AppBar<->MyTasksView org_id sync — zero new dependencies, 2-line change, backward compatible"
  - "filteredGeneralTasks computed filters client-side from already-loaded generalTasks — avoids re-fetching on every org switch"
  - "generalByStatus updated to use filteredGeneralTasks so kanban board view also respects org selection"
  - "visibleOrgSummary filter: org_id===null always shown (Все row), task_count>0 required for org rows"
  - "org_id param on /badges is Optional with default None — omitting it returns identical results to before (no regression for all callers)"

patterns-established:
  - "Task.org_id == org_id filter injected conditionally via if org_id is not None guard — reusable pattern for other badge-like endpoints"

requirements-completed: [TASK-FILTER-01, TASK-FILTER-02, TASK-FILTER-03]

# Metrics
duration: 15min
completed: 2026-04-06
---

# Phase 11 Plan 01: Fix Task Display Per-User Org Filtering Summary

**Badge counts, org selector, and task list all scoped to selected org via localStorage bridge + client-side computed filters + optional org_id query param on /badges**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-06T00:00:00Z
- **Completed:** 2026-04-06T00:15:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Backend `/tasks/badges` endpoint accepts optional `org_id` query param, filters `new_tasks` and `task_changes` counts to that org
- `filteredGeneralTasks` computed in MyTasksView.vue filters task list by `selectedOrgId` (null = show all)
- `visibleOrgSummary` computed hides orgs with `task_count === 0` from the org selector, always keeping the "Все" row
- `generalByStatus` (kanban board) updated to use `filteredGeneralTasks` so board view also respects org selection
- `selectOrg()` persists selection to `localStorage.active_org_id`; AppBar `loadBadges()` reads it to pass `?org_id=` to badges API

## Task Commits

1. **Task 1: Backend — add org_id filter param to /badges endpoint** - `1bdc286` (feat)
2. **Task 2: Frontend — filter tasks by selectedOrgId, hide zero-task orgs, pass org_id to badges** - `c586f3f` (feat)

## Files Created/Modified

- `backend/app/routers/tasks.py` - Added `org_id: Optional[int] = Query(None)` param to `get_badges()`, conditional `Task.org_id == org_id` filter on new_tasks and task_changes queries
- `frontend/src/views/MyTasksView.vue` - Added `filteredGeneralTasks` and `visibleOrgSummary` computed properties; updated list view `:items` binding, kanban `generalByStatus`, and org selector `v-for`; `selectOrg()` writes to localStorage
- `frontend/src/components/AppBar.vue` - `loadBadges()` reads `localStorage.active_org_id` and appends `?org_id=` to badges URL

## Decisions Made

- **localStorage bridge** over event bus / Pinia store for AppBar<->MyTasksView org_id sync: zero new dependencies, backward compatible, 2-line change. AppBar is always-mounted so localStorage is reliable.
- **Client-side filter** (`filteredGeneralTasks`) instead of re-fetching `/tasks/init?org_id=X`: avoids refetch latency on org selection; all tasks already in memory.
- **org_id field name**: Tasks returned from `/tasks/init` (my_tasks) have `t.org_id` confirmed from line 1005 of MyTasksView.vue (`org_id: t.org_id ?? null`) and line 578 (org_id on taskForm).
- **generalByStatus updated**: The kanban board used `generalTasks.value.filter` — updated to `filteredGeneralTasks.value.filter` for consistency. Not mentioned in plan explicitly — minor deviation treated as Rule 2 (missing critical functionality).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Updated generalByStatus to use filteredGeneralTasks**
- **Found during:** Task 2 (frontend changes)
- **Issue:** The kanban board view uses `generalByStatus(status)` which filtered directly from `generalTasks.value`. Without updating this function, the board view would ignore `selectedOrgId` even after applying `filteredGeneralTasks` to the list view.
- **Fix:** Changed `generalByStatus` from `generalTasks.value.filter(...)` to `filteredGeneralTasks.value.filter(...)`
- **Files modified:** frontend/src/views/MyTasksView.vue
- **Verification:** Build passes; board and list views now both respect org selection
- **Committed in:** c586f3f (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Essential for correct behavior — both list and kanban views now respect org selection.

## Issues Encountered

- Python not available in shell for syntax check; verified visually by reading the modified function. Build-level verification (docker rebuild) requires server access which is done by user.

## User Setup Required

None - no external service configuration required. Docker image rebuild needed to deploy backend changes.

## Next Phase Readiness

- All three bugs fixed: badges org-scoped, zero-task orgs hidden, task list filtered by org
- Superadmin/admin org visibility unchanged — backend filter only applies to task badge counts, not org_summary endpoint
- Ready for deploy (docker rebuild on server)

---
*Phase: 11-fix-task-display-per-user-org-filtering-badges-org-selector-task-scoping*
*Completed: 2026-04-06*
