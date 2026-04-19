---
phase: 16-refactor-monoliths
plan: "02"
subsystem: backend
tags: [refactor, purchases, excel-export, import]
dependency_graph:
  requires: [16-01]
  provides: [purchase_export.py]
  affects: [purchases.py, app/__init__.py]
tech_stack:
  added: []
  patterns: [APIRouter extraction, same-prefix dual-router]
key_files:
  created:
    - backend/app/routers/purchase_export.py
  modified:
    - backend/app/routers/purchases.py
    - backend/app/__init__.py
decisions:
  - "Removed lines 189-321 (constants) + 1529-1840 (export endpoints) from purchases.py; CRUD block 322-1528 preserved"
  - "purchase_export.router shares prefix /api/purchases — FastAPI merges routes transparently"
  - "FeoCategory import moved inline in POST /import to avoid circular import risk"
metrics:
  duration: "~20 min"
  completed: "2026-04-19"
  tasks_completed: 3
  files_changed: 3
---

# Phase 16 Plan 02: Purchase Export Extract Summary

Extracted Excel export + Scroller-format payment import from `purchases.py` into standalone `purchase_export.py`. First atomic Wave-1 extract — validates the pattern for subsequent modules.

## What Was Done

### Task 1 — Create purchase_export.py
- New file: `backend/app/routers/purchase_export.py` (478 lines)
- Contains: `ALL_EXPORT_COLUMNS`, `DEFAULT_EXPORT_COLUMNS`, 4 label dicts, `_get_cell_value` helper
- Endpoints: `GET /export/columns`, `GET /export/excel`, `GET /import/template`, `POST /import`
- `router = APIRouter(prefix="/api/purchases", tags=["purchase-export"])`
- Commit: `53102fe`

### Task 2 — Remove extracted code from purchases.py
- Removed constants block (lines 189-321) and export endpoints (lines 1529-1840)
- purchases.py: 3233 → 2787 lines (-446)
- Zero remaining references to `ALL_EXPORT_COLUMNS` in purchases.py
- Commit: `57da63c` (combined with Task 3)

### Task 3 — Register router in __init__.py
- Added `purchase_export` to batch import
- Added `app.include_router(purchase_export.router)` after `purchase_approvals.router`
- Commit: `57da63c`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Initial Task 2 deleted CRUD endpoints along with export block**
- **Found during:** Task 2 verification (pytest gate)
- **Issue:** Range 189-1841 included CRUD endpoints (lines 322-1528) — `GET /`, `POST /`, `PUT /`, etc. — not just export code. 3 tests failed: `/api/purchases/ 404`, members, transitions.
- **Fix:** Reconstructed purchases.py as `head(1-188) + crud_block(322-1528 from git) + tail(items_import+onward)`. Result: 2787 lines. All 17 tests green.
- **Files modified:** `backend/app/routers/purchases.py`
- **Commit:** `57da63c`

## Self-Check

- [x] `backend/app/routers/purchase_export.py` exists (478 lines >= 200)
- [x] `backend/app/routers/purchases.py` = 2787 lines (< 3233)
- [x] `grep -c "ALL_EXPORT_COLUMNS" purchases.py` = 0
- [x] `app.include_router(purchase_export.router)` present in __init__.py
- [x] `pytest tests/test_routers_mounted.py -q` → 17 passed, 0 failed

## Self-Check: PASSED
