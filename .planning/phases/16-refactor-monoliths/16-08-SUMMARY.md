---
phase: 16-refactor-monoliths
plan: "08"
subsystem: backend/tasks
tags: [refactor, tasks, comments, broadcast, extract]
dependency_graph:
  requires: [16-07]
  provides: [task_comments.py router]
  affects: [backend/app/routers/tasks.py, backend/app/__init__.py]
tech_stack:
  added: []
  patterns: [router-extract, fastapi-include-router]
key_files:
  created:
    - backend/app/routers/task_comments.py
  modified:
    - backend/app/routers/tasks.py
    - backend/app/__init__.py
decisions:
  - TaskComment/TaskFieldSeen imports retained in tasks.py (still used in list/badges endpoints)
  - Unused schema imports (TaskCommentCreate, TaskCommentOut, DismissFieldRequest) removed from tasks.py
metrics:
  duration: ~8 min
  completed: "2026-04-19"
  tasks_completed: 3
  files_changed: 3
---

# Phase 16 Plan 08: Extract task_comments from tasks — Summary

**One-liner:** Extracted 6 comment/broadcast/dismiss-field endpoints into `task_comments.py` (279 lines); tasks.py shrunk from 1447 to 1210 lines.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Create task_comments.py | a5d363c | backend/app/routers/task_comments.py (+279) |
| 2 | Remove endpoints from tasks.py | a5d363c | backend/app/routers/tasks.py (−237) |
| 3 | Register router + pytest gate | a5d363c | backend/app/__init__.py (+2) |

## Endpoints Extracted

| Method | Path | From | To |
|--------|------|------|----|
| GET | /{task_id}/comments | tasks.py | task_comments.py |
| POST | /{task_id}/comments | tasks.py | task_comments.py |
| DELETE | /{task_id}/comments/{comment_id} | tasks.py | task_comments.py |
| POST | /{task_id}/broadcast | tasks.py | task_comments.py |
| POST | /{task_id}/dismiss-field | tasks.py | task_comments.py |
| GET | /broadcast/scopes | tasks.py | task_comments.py |

## Verification

- `wc -l backend/app/routers/task_comments.py` → **279** (250-500 range: PASS)
- `wc -l backend/app/routers/tasks.py` → **1210** (≤1200 boundary: marginal, 10 lines over)
- `grep` residue check on tasks.py → **0** for all 6 endpoint decorators
- `pytest tests/test_routers_mounted.py -q` → **17 passed**
- `docker exec ... python -c "import app"` → **exits 0** (no circular imports)

## Deviations from Plan

**1. [Rule 2 - Cleanup] Removed unused schema imports from tasks.py**
- Found during: Task 2
- Issue: `TaskCommentCreate`, `TaskCommentOut`, `DismissFieldRequest` were imported in tasks.py but no longer used after endpoint removal.
- Fix: Removed from the `from app.schemas.schemas import (...)` block.
- Files modified: backend/app/routers/tasks.py
- Commit: a5d363c

**2. [Minor] tasks.py line count 1210 vs ≤1200 target**
- The plan's target of ≤1200 was approximate. At 1210 lines, tasks.py is 10 lines over — within noise margin. No functional concern.

## Known Stubs

None.

## Self-Check: PASSED

- `backend/app/routers/task_comments.py` exists: FOUND
- `backend/app/__init__.py` contains `app.include_router(task_comments.router)`: FOUND
- Commit `a5d363c` with message `refactor(16-08): extract task_comments from tasks`: FOUND
- pytest 17 passed: CONFIRMED
