---
phase: 16-refactor-monoliths
plan: "04"
subsystem: backend/purchases
tags: [refactor, helper-module, budget-validation, framework-seq]
dependency_graph:
  requires: [16-01]
  provides: [purchase_budget helpers for 16-06]
  affects: [backend/app/routers/purchases.py]
tech_stack:
  added: []
  patterns: [helper-only module, no APIRouter, shared import]
key_files:
  created:
    - backend/app/routers/purchase_budget.py
  modified:
    - backend/app/routers/purchases.py
decisions:
  - "D-05 applied: shared helpers in dedicated module to avoid circular imports with future purchase_transitions.py"
  - "D-19 applied: helpers stay in originating module (purchase_budget.py), callers import from there"
  - "No FEO cap helpers found in purchases.py — grep confirmed 0 matches; purchase_budget.py notes this for future additions"
  - "Module not registered in __init__.py — helper-only, no router"
metrics:
  duration: "~10 minutes"
  completed_date: "2026-04-19"
  tasks_completed: 3
  files_changed: 2
---

# Phase 16 Plan 04: Extract purchase_budget Helpers Summary

**One-liner:** Extracted `FRAMEWORK_TYPES`, `_assign_framework_seq`, `_check_budget` from purchases.py into a helper-only module `purchase_budget.py` (no router, no endpoints).

## What Was Built

`backend/app/routers/purchase_budget.py` — 125-line helper module containing:
- `FRAMEWORK_TYPES: set` — contract types that trigger framework sequencing
- `async _assign_framework_seq(p, db, exclude_id)` — auto-fills `framework_seq` on a Purchase
- `async _check_budget(subsidy_id, amount, exclude_pid, db)` — raises HTTP 422 if subsidy budget exceeded

`backend/app/routers/purchases.py` — shrunk from 1556 to 1508 lines (-48 lines); imports the three identifiers via `from app.routers.purchase_budget import _check_budget, _assign_framework_seq, FRAMEWORK_TYPES`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create purchase_budget.py helper module | 4603a07 | backend/app/routers/purchase_budget.py (+125) |
| 2 | Remove moved helpers from purchases.py and import | a6b414b | backend/app/routers/purchases.py (-48 lines +1 import) |
| 3 | Verify build + smoke test + commit | a6b414b | pytest 17/17 passed |

## Verification Results

- `docker exec vsks_crm-backend-1 python -c "from app.routers.purchase_budget import _check_budget, _assign_framework_seq, FRAMEWORK_TYPES; print('ok')"` → ok
- `pytest tests/test_routers_mounted.py -q` → **17 passed**
- `grep -c "purchase_budget" backend/app/__init__.py` → 0 (not registered — helper-only)
- `wc -l backend/app/routers/purchase_budget.py` → 125 (within 100-250 range)
- `grep -c "def _check_budget" backend/app/routers/purchases.py` → 0
- `grep -c "def _assign_framework_seq" backend/app/routers/purchases.py` → 0
- `grep -c "^FRAMEWORK_TYPES = " backend/app/routers/purchases.py` → 0
- `grep -c "from app.routers.purchase_budget import" backend/app/routers/purchases.py` → 1

## Deviations from Plan

None — plan executed exactly as written.

Note: No FEO cap helpers were found in purchases.py (grep for `feo_cap`, `FEO_CAP`, `feo_limit` returned 0 matches). This is documented in purchase_budget.py for future reference.

## Known Stubs

None.

## Self-Check: PASSED

- `backend/app/routers/purchase_budget.py` — FOUND
- commit 4603a07 — FOUND
- commit a6b414b — FOUND
- pytest 17 passed — CONFIRMED
