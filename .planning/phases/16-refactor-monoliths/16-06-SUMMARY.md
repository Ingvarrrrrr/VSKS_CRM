---
phase: 16-refactor-monoliths
plan: "06"
subsystem: purchases
tags: [refactor, extraction, state-machine, purchases]
dependency_graph:
  requires: [16-01, 16-04, 16-05]
  provides: [purchase_transitions module]
  affects: [purchases.py, app/__init__.py]
tech_stack:
  added: []
  patterns: [router-per-concern, import-back pattern (STATUS_ORDER stays in source)]
key_files:
  created:
    - backend/app/routers/purchase_transitions.py
  modified:
    - backend/app/routers/purchases.py
    - backend/app/app/__init__.py
decisions:
  - TRANSITION_REQUIRED moved to purchase_transitions.py (G-08: only used by transition endpoint)
  - STATUS_ORDER stays in purchases.py (G-08: used by CRUD, members, my-tasks)
  - purchase_transitions.py imports STATUS_ORDER back from purchases (no redefinition)
  - _check_budget/_assign_framework_seq imported from purchase_budget (D-05)
metrics:
  duration: ~10min
  completed: 2026-04-19
  tasks_completed: 3
  files_created: 1
  files_modified: 2
---

# Phase 16 Plan 06: Purchase Transitions Extraction Summary

**One-liner:** State-machine transitions (POST /{pid}/transition + convert-to-order) + TRANSITION_REQUIRED dict extracted into standalone `purchase_transitions.py` — last purchases.py decomposition step.

## What Was Done

- Created `backend/app/routers/purchase_transitions.py` (264 lines) with:
  - `TRANSITION_REQUIRED` dict (G-08)
  - `transition_status` endpoint (`POST /{pid}/transition`)
  - `convert_service_note_to_order` endpoint (`POST /{pid}/convert-to-order`)
- Removed both functions and TRANSITION_REQUIRED from `purchases.py`
- `purchases.py`: 1217 lines → 980 lines (−237 lines)
- Registered `purchase_transitions.router` in `backend/app/__init__.py`
- pytest 17/17 passed after extraction

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Verification

- `wc -l backend/app/routers/purchase_transitions.py` = 264 (within 200-400 range)
- `wc -l backend/app/routers/purchases.py` = 980 (≤ 1550 target)
- `grep -c "^STATUS_ORDER = " backend/app/routers/purchases.py` = 1 (preserved)
- `grep -c "TRANSITION_REQUIRED" backend/app/routers/purchases.py` = 0 (removed)
- `docker exec vsks_crm-backend-1 pytest /app/tests/test_routers_mounted.py -q` → 17 passed

## Remaining purchases.py Candidates (D-03 target ≤ 800)

purchases.py is now 980 lines. Remaining candidates for future extraction (not in scope of 16-06):
- `/{pid}/tasks` GET endpoint (~10 lines)
- `/{pid}/members` GET/POST/DELETE endpoints (~60 lines)
- `my-tasks` / `list_purchases_for_my_tasks` (~50 lines)
- Various CRUD list/get/update/delete endpoints

## Self-Check: PASSED

- `backend/app/routers/purchase_transitions.py` — FOUND
- `backend/app/routers/purchases.py` — FOUND, STATUS_ORDER preserved, TRANSITION_REQUIRED absent
- `backend/app/__init__.py` — contains `app.include_router(purchase_transitions.router)`
- Commit c7b483b — FOUND
