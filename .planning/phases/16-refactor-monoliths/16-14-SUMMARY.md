---
phase: 16-refactor-monoliths
plan: 14
subsystem: frontend/my-tasks
tags: [refactor, vue-components, purchases, kanban]
dependency_graph:
  requires: [16-12]
  provides: [PurchasesTable.vue, PurchasesKanban.vue]
  affects: [MyTasksView.vue]
tech_stack:
  added: []
  patterns: [SFC extraction, props-down/emits-up, optimistic drag-drop]
key_files:
  created:
    - frontend/src/components/my-tasks/PurchasesTable.vue
    - frontend/src/components/my-tasks/PurchasesKanban.vue
  modified:
    - frontend/src/views/MyTasksView.vue
decisions:
  - Used `v-table` (not `v-data-table`) matching the original purchases list code
  - PurchasesKanban receives `archivePurchases` as separate prop (parallel to tasks/archiveTasks split in parent)
  - handleUpdateKanbanStatus in parent does optimistic PATCH with full rollback on error
  - Subsidy filter moved into PurchasesKanban as local state (no prop needed — derived from purchases array)
metrics:
  duration: 25m
  completed: 2026-04-19
  tasks_completed: 3
  files_created: 2
  files_modified: 1
---

# Phase 16 Plan 14: Extract PurchasesTable + PurchasesKanban from MyTasksView Summary

**One-liner:** Extracted purchases list (`v-table`) and kanban board (drag-drop columns by status) into two typed Vue 3 SFCs; MyTasksView reduced 1811 → 1736 lines.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create PurchasesTable.vue | 5293f94 | frontend/src/components/my-tasks/PurchasesTable.vue |
| 2 | Create PurchasesKanban.vue | 5293f94 | frontend/src/components/my-tasks/PurchasesKanban.vue |
| 3 | Wire into MyTasksView + verify | 5293f94 | frontend/src/views/MyTasksView.vue |

## Artifacts

| File | Lines | Role |
|------|-------|------|
| PurchasesTable.vue | 263 | v-table list view, typed Purchase interface, open-purchase emit |
| PurchasesKanban.vue | 349 | Kanban columns by status, drag-drop, subsidy filter local state |
| MyTasksView.vue | 1736 | Parent — wires both, holds onDrop logic + handleUpdateKanbanStatus |

## Verification Results

- `wc -l PurchasesTable.vue` = 263 (>= 250 required)
- `wc -l PurchasesKanban.vue` = 349 (>= 250 required)
- `wc -l MyTasksView.vue` = 1736 (<= 900 NOT yet — Plan 16-15 targets <= 600)
- `docker exec vsks_crm-frontend-1 npm run build` — exit 0, zero TypeScript errors
- `pytest 17 passed`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Design] PurchasesKanban takes `archivePurchases` as explicit prop**
- **Found during:** Task 2
- **Issue:** Parent splits purchases into `tasks` (active) and `archiveTasks` (paid). Kanban needs both to populate columns. Could not derive archive from a single array without carrying the parent's split logic.
- **Fix:** Added `archivePurchases: Purchase[]` and `showArchive: boolean` as props (matching parent's existing refs).
- **Files modified:** PurchasesKanban.vue, MyTasksView.vue
- **Commit:** 5293f94

**2. [Rule 1 - Accuracy] Used `v-table` not `v-data-table` for list view**
- **Found during:** Task 1
- **Issue:** The plan acceptance criteria mentioned `v-data-table` but the original inline code used `v-table` (Vuetify's simpler table). Using `v-data-table` would change behaviour.
- **Fix:** Kept `v-table` matching the original — preserves identical visual output.
- **Commit:** 5293f94

## Known Stubs

None — purchases data flows from parent's `tasks`/`archiveTasks` refs which are populated by real API calls.

## Self-Check: PASSED

- [x] `frontend/src/components/my-tasks/PurchasesTable.vue` exists (263 lines)
- [x] `frontend/src/components/my-tasks/PurchasesKanban.vue` exists (349 lines)
- [x] Commit 5293f94 exists
- [x] Build exit 0
- [x] pytest 17/17
