---
phase: 06-analytics-budget-history
plan: 03
subsystem: frontend
tags: [vue3, vuetify, timeline, budget-history, dialog, audit-log]

# Dependency graph
requires:
  - phase: 06-01
    provides: budget_history table with audit rows
  - phase: 06-02
    provides: GET /api/subsidies/{id}/history paginated endpoint
provides:
  - BudgetHistoryDialog.vue component with v-timeline
  - History button wired into each SubsidiesView subsidy card
affects: [06-analytics-budget-history]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "defineExpose({ open }) pattern for imperative dialog trigger (no modelValue prop)"
    - "ref<InstanceType<typeof Component> | null>(null) for typed component refs"
    - "apiFetch with offset/limit pagination and push(...items) for load-more"

key-files:
  created:
    - frontend/src/components/BudgetHistoryDialog.vue
  modified:
    - frontend/src/views/SubsidiesView.vue

key-decisions:
  - "Used open() expose pattern (not modelValue v-model) — simpler for slot-less imperative trigger from parent"
  - "dot-color orange for entity_type='subsidy', blue for entity_type='purchase' — matches plan spec"
  - "History button placed between approvers button and pencil button in subsidy card action row"
  - "BudgetDrillDownDialog FEO drill verified: dashboard.py builds nested children tree; __init__.py mounts router at line 288"

requirements-completed: [BUDGET-09]

# Metrics
duration: 3min
completed: 2026-04-04
---

# Phase 6 Plan 03: Budget History Timeline UI Summary

**BudgetHistoryDialog.vue created with Vuetify v-timeline and wired into SubsidiesView.vue subsidy cards — users can view paginated audit trail of budget changes for any subsidy**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-04-04T07:26:16Z
- **Completed:** 2026-04-04T07:28:52Z
- **Tasks:** 3 (2 code tasks + 1 verification task)
- **Files created:** 1
- **Files modified:** 1

## Accomplishments

- Created `frontend/src/components/BudgetHistoryDialog.vue`: 139 lines, uses `v-timeline density="compact" side="end"`, loading/empty/populated states, load-more pagination, `open()` method exposed via `defineExpose`
- Updated `frontend/src/views/SubsidiesView.vue`: import added, `historyDialogRef` typed ref declared, `openHistoryDialog(s)` function added, `mdi-history` button in subsidy card, `<BudgetHistoryDialog ref="historyDialogRef" />` registered in template
- Verified `BudgetDrillDownDialog.vue` has 15 occurrences of `drillStack`/`children` covering all 3 FEO drill levels
- Verified `dashboard.py` builds nested `children` tree with rollup for all FEO levels
- Verified `app.include_router(dashboard.router)` at line 288 in `__init__.py`
- Frontend build passes: `npm run build` completes in ~15s with zero TypeScript errors

## Task Commits

1. **Task 1: Create BudgetHistoryDialog.vue** - `09d3a35` (feat)
2. **Task 2: Wire BudgetHistoryDialog into SubsidiesView.vue** - `35860ae` (feat)
3. **Task 3: Verify BudgetDrillDownDialog FEO drill-down** - verification only, no code change

## Files Created/Modified

- `frontend/src/components/BudgetHistoryDialog.vue` — Created (139 lines): v-timeline dialog with loading/empty/paginated states and imperative open() method
- `frontend/src/views/SubsidiesView.vue` — Modified (12 lines added): import, ref, function, history button, dialog registration

## Decisions Made

- `open()` expose pattern chosen over `v-model` — simpler for imperative trigger from parent; no need for a separate boolean ref in SubsidiesView
- History button placed between `mdi-account-multiple` (approvers) and `mdi-pencil` (edit) for logical grouping of informational vs. edit actions
- `dot-color` = orange for `entity_type === 'subsidy'`, blue for `entity_type === 'purchase'` per plan specification

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

| Check | Result |
|-------|--------|
| BudgetHistoryDialog.vue has v-timeline | PASS |
| BudgetHistoryDialog.vue has "Изменений ещё не было" | PASS |
| BudgetHistoryDialog.vue has defineExpose | PASS |
| SubsidiesView.vue has BudgetHistoryDialog import | PASS |
| SubsidiesView.vue has historyDialogRef | PASS |
| SubsidiesView.vue has openHistoryDialog | PASS |
| SubsidiesView.vue has mdi-history button | PASS |
| Frontend build passes | PASS |
| drillStack + children in BudgetDrillDownDialog.vue | PASS (15 occurrences) |
| dashboard router mounted in __init__.py | PASS (line 288) |
| dashboard.py returns children-nested tree | PASS (lines 81, 90, 96) |

## User Setup Required

Docker image rebuild required for changes to be live:
```bash
docker compose build frontend && docker compose up -d frontend
```

After rebuild: Open SubsidiesView → each subsidy card has a clock/history icon button → click opens BudgetHistoryDialog timeline.

## Next Phase Readiness

- Phase 06 plan 03 complete — budget history UI timeline is ready
- Phase 06 (analytics + budget history) is now fully implemented
- Ready for Phase 07: Wishes lifecycle implementation

---

## Self-Check

*Files exist:*
- `frontend/src/components/BudgetHistoryDialog.vue` — created in this plan
- `frontend/src/views/SubsidiesView.vue` — modified in this plan

*Commits exist:*
- `09d3a35` — feat(06-03): create BudgetHistoryDialog.vue component
- `35860ae` — feat(06-03): wire BudgetHistoryDialog into SubsidiesView.vue

## Self-Check: PASSED

---
*Phase: 06-analytics-budget-history*
*Completed: 2026-04-04*
