---
phase: 15-reusable-purchase-items-editor
plan: 02
subsystem: ui
tags: [vue, dead-code, cleanup, components]

# Dependency graph
requires: []
provides:
  - "OrderProductsTable.vue (285 lines, dead code) removed from frontend/src/components/"
affects:
  - 15-reusable-purchase-items-editor (clears a confusing dead-code component before PurchaseItemsEditor lands)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dead-code audit: grep -r across frontend/src/ excluding .backup.vue before deletion"

key-files:
  created: []
  modified: []

key-decisions:
  - "OrderProductsTable.vue confirmed dead — only reference was CreateOrderView.backup.vue (itself dead); deletion safe"
  - "Other dead-code files (AddProductDialog×3, ProductSelector×3, CreateOrderViewSimple, CreateOrderView.backup) kept in-tree — out of scope for Phase 15, tracked in 04_TODO.md for a dedicated cleanup phase"

patterns-established:
  - "Pre-deletion audit: always grep live source files (excluding *.backup.*) before removing a component"

requirements-completed:
  - ITEMS-EDITOR-08

# Metrics
duration: 5min
completed: 2026-04-19
---

# Phase 15 Plan 02: OrderProductsTable.vue Dead-Code Deletion Summary

**285-line OrderProductsTable.vue (Vue 2-style, OrderProduct shape) confirmed dead and deleted; frontend build passes cleanly**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-19T12:20:00Z
- **Completed:** 2026-04-19T12:25:00Z
- **Tasks:** 1
- **Files modified:** 1 (deleted)

## Accomplishments

- Live-reference audit returned 0 matches (only `CreateOrderView.backup.vue` referenced it — itself dead)
- `frontend/src/components/OrderProductsTable.vue` deleted (285 lines)
- `cd frontend && npm run build` exited 0 — build green after deletion

## Grep Audit Output

```
# Command run:
grep -r "OrderProductsTable" frontend/src/ --include="*.vue" --include="*.ts" --include="*.js" | grep -v ".backup.vue" | grep -v "OrderProductsTable.vue"

# Result: (empty — 0 live references)

# Full audit (all files including backup):
frontend/src/views/CreateOrderView.backup.vue:import OrderProductsTable from '../components/OrderProductsTable.vue'
# → Only reference is in .backup.vue (dead code itself)
```

## File Stats Before Deletion

```
wc -l frontend/src/components/OrderProductsTable.vue
285 frontend/src/components/OrderProductsTable.vue
```

(Template line count was 285 lines + 1 terminal newline = 286 in git diff, consistent with plan estimate of ~285.)

## Task Commits

Each task was committed atomically:

1. **Task 1: Confirm OrderProductsTable.vue has no live importers, then delete** - `dd115c0` (chore)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `frontend/src/components/OrderProductsTable.vue` — DELETED (285 lines removed)

## Decisions Made

- Deletion confirmed safe: 0 live importers found.
- `CreateOrderView.backup.vue` retains its import reference (stale) — it is itself dead code and is handled by a future cleanup phase, not Phase 15.
- Other dead-code duplicates intentionally left in-tree (out of scope):
  - `AddProductDialog.vue` × 3 variants
  - `ProductSelector.vue` × 3 variants
  - `CreateOrderViewSimple.vue`
  - `CreateOrderView.backup.vue`
  - `DashboardViewSimple.vue`
  These are tracked in `04_TODO.md` for a dedicated housekeeping phase.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. Grep audit, deletion, and build all completed without issues.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Dead-code item cleared; `frontend/src/components/` is cleaner before `PurchaseItemsEditor.vue` lands in Plans 15-03+.
- No blockers introduced.

## Known Stubs

None — this plan only deletes a file; no stubs introduced.

---
*Phase: 15-reusable-purchase-items-editor*
*Completed: 2026-04-19*
