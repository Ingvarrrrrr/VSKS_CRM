---
phase: 16-refactor-monoliths
plan: 05
subsystem: backend/purchases
tags: [refactor, extraction, purchase_members, assignment, consent, kanban]
dependency_graph:
  requires: [16-01, 16-04]
  provides: [purchase_members router with assign/consent/kanban/substatus/comment endpoints]
  affects: [purchases.py, app/__init__.py]
tech_stack:
  added: [backend/app/routers/purchase_members.py]
  patterns: [FastAPI APIRouter prefix=/api/purchases, async SQLAlchemy 2.0, Depends(get_current_user)]
key_files:
  created: [backend/app/routers/purchase_members.py]
  modified: [backend/app/routers/purchases.py, backend/app/__init__.py]
decisions:
  - _create_assignment_chat_room moved to purchase_members.py (G-05: self-contained)
  - Unused chat_manager + ChatMessage top-level imports cleaned from purchases.py
  - Single atomic commit for all 3 files (Task 1+2+3 combined per 16-02 pattern)
metrics:
  duration: ~15 minutes
  completed: 2026-04-20T05:18:01Z
  tasks_completed: 3
  files_modified: 3
---

# Phase 16 Plan 05: Purchase Members Extraction Summary

**One-liner:** Extracted assign/consent/kanban-status/substatus/comment endpoints + `_create_assignment_chat_room` helper into `purchase_members.py` (341 lines), purchases.py reduced from 1508 to 1217 lines.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create purchase_members.py | c70a78c | backend/app/routers/purchase_members.py (created, 341 lines) |
| 2 | Remove moved code from purchases.py | c70a78c | backend/app/routers/purchases.py (1508 -> 1217 lines) |
| 3 | Register purchase_members.router in __init__.py | c70a78c | backend/app/__init__.py |

## Verification

- `pytest tests/test_routers_mounted.py -q`: **17 passed**
- `wc -l backend/app/routers/purchase_members.py`: **341** (within 250-500 target)
- `wc -l backend/app/routers/purchases.py`: **1217** (reduced by 291 lines)
- `grep "app.include_router(purchase_members.router)"` in __init__.py: found
- All 5 endpoints present in purchase_members.py: assign, consent, kanban-status, substatus, comment
- `def _create_assignment_chat_room` present in purchase_members.py
- `from app.routers.purchases import _purchase_to_full, STATUS_ORDER` in purchase_members.py

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Cleanup] Removed unused top-level imports from purchases.py**
- **Found during:** Task 2 (removing moved code)
- **Issue:** `from app.chat_manager import manager as chat_manager`, `from app.models.chat_room import ChatRoom, ChatParticipant`, `from app.models.chat_message import ChatMessage` were only used by the moved endpoints
- **Fix:** Removed the 3 unused top-level import lines from purchases.py
- **Files modified:** backend/app/routers/purchases.py
- **Commit:** c70a78c

## Known Stubs

None.

## Self-Check: PASSED

- `backend/app/routers/purchase_members.py`: FOUND (341 lines)
- `backend/app/__init__.py` contains `purchase_members`: FOUND
- commit `c70a78c`: FOUND in git log
- pytest 17 passed: CONFIRMED
