---
phase: 08-торговые-площадки
plan: "03"
subsystem: frontend/publications
tags: [vue, publications, roseltorg, procedure-type, dialog]
dependency_graph:
  requires: []
  provides: [procedure_type in publish API request]
  affects: [CreateOrderView.vue, /api/publications/purchases/{id}]
tech_stack:
  added: []
  patterns: [two-step dialog with v-expand-transition, conditional v-btn rendering]
key_files:
  created: []
  modified:
    - frontend/src/views/CreateOrderView.vue
decisions:
  - Росэлторг uses two-step publish: first click sets pendingPlatform, second step shows dropdown + confirm
  - Фабрикант remains single-step (direct doPublish call)
  - Close button now resets pendingPlatform and roseltorgProcedureType for clean state
metrics:
  duration: "~5 min"
  completed: "2026-03-20"
  tasks_completed: 1
  files_modified: 1
---

# Phase 8 Plan 03: Росэлторг Procedure Type Dropdown Summary

**One-liner:** Added two-step publish dialog for Росэлторг with mandatory procedure_type dropdown (4 types) before confirming publication.

## What Was Built

- New refs: `pendingPlatform`, `roseltorgProcedureType`
- New constant: `ROSELTORG_PROCEDURE_TYPES` with 4 procedure types
- Two-step flow for Росэлторг: clicking "Опубликовать" sets `pendingPlatform = 'roseltorg_rb'`, which reveals a `v-select` dropdown
- Confirm button is disabled until procedure type is selected
- `doPublish` updated to accept optional `procedureType` param; sends `body.procedure_type` to API when provided
- Фабрикант publish flow unchanged (direct `doPublish(platform)` call)
- Close button resets both `pendingPlatform` and `roseltorgProcedureType` for clean dialog state

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add procedure_type dropdown in publish dialog | 8171a82 | frontend/src/views/CreateOrderView.vue |

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- `frontend/src/views/CreateOrderView.vue` modified: FOUND
- Commit 8171a82: FOUND
- All required patterns present (roseltorgProcedureType, pendingPlatform, ROSELTORG_PROCEDURE_TYPES, procedure_type)
- TypeScript compilation: no errors
