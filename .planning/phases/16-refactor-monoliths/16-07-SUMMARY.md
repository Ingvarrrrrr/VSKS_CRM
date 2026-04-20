---
phase: 16-refactor-monoliths
plan: "07"
subsystem: backend/tasks
tags: [refactor, extraction, helper-module, task-visibility]
dependency_graph:
  requires: [16-01]
  provides: [task_visibility helpers for 16-08, 16-09, 16-10, 16-11]
  affects: [backend/app/routers/tasks.py, backend/app/routers/task_visibility.py]
tech_stack:
  added: []
  patterns: [helper-only-module, import-back-pattern]
key_files:
  created:
    - backend/app/routers/task_visibility.py
  modified:
    - backend/app/routers/tasks.py
decisions:
  - "helper-only module: no APIRouter, no include_router, not in __init__.py"
  - "purchases.py cross-file import left intact for Plan 16-11 (tasks.py re-exports via its own import)"
metrics:
  duration: ~8m
  completed: "2026-04-20T05:12:33Z"
  tasks_completed: 3
  files_modified: 2
---

# Phase 16 Plan 07: Extract task_visibility helpers from tasks Summary

**One-liner:** Extracted `_get_visible_user_ids`, `_enrich_tasks`, `_create_task_chat_room` into `task_visibility.py` helper-only module (291 lines); `tasks.py` reduced from 1698 to 1447 lines with import-back pattern preserving cross-file compatibility for Plan 16-11.

## What Was Done

- Created `backend/app/routers/task_visibility.py` (291 lines) — pure helper module with no router, no endpoints
- Moved three helpers byte-for-byte: `_get_visible_user_ids`, `_create_task_chat_room`, `_enrich_tasks`
- Updated `tasks.py` to import all three: `from app.routers.task_visibility import _get_visible_user_ids, _enrich_tasks, _create_task_chat_room`
- `purchases.py` cross-file import (`from app.routers.tasks import _enrich_tasks`) remains valid — tasks.py re-exports the name via its own import (Plan 16-11 will update it directly)

## Commits

| Hash | Message | Files |
|------|---------|-------|
| adfed1a | refactor(16-07): extract task_visibility helpers from tasks | task_visibility.py (new, +292), tasks.py (modified, -252 net) |

## Verification Results

- `grep -c "APIRouter" backend/app/routers/task_visibility.py` → 0
- `grep -c "@router." backend/app/routers/task_visibility.py` → 0
- `grep -c "task_visibility" backend/app/__init__.py` → 0
- `wc -l backend/app/routers/task_visibility.py` → 291 (in range 150-300)
- `wc -l backend/app/routers/tasks.py` → 1447 (≤1500)
- `docker exec vsks_crm-backend-1 python -c "from app.routers.task_visibility import _get_visible_user_ids, _enrich_tasks, _create_task_chat_room; print('ok')"` → ok
- `pytest tests/test_routers_mounted.py -q` → **17 passed**

## Deviations from Plan

None — plan executed exactly as written. APIRouter mention removed from docstring comment to satisfy strict grep check (was in comment, not code).

## Known Stubs

None.

## Self-Check: PASSED

- `backend/app/routers/task_visibility.py` — FOUND
- Commit `adfed1a` — FOUND (`git log --oneline -3` confirms)
- 17 pytest passed — VERIFIED
