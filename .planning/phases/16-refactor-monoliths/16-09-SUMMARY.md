---
phase: 16-refactor-monoliths
plan: "09"
subsystem: backend/tasks
tags: [refactor, task-badges, extraction, D-11]
dependency_graph:
  requires: [16-07]
  provides: [task_badges router]
  affects: [backend/app/__init__.py, backend/app/routers/tasks.py]
tech_stack:
  added: []
  patterns: [router-per-concern, helper-import-from-visibility]
key_files:
  created:
    - backend/app/routers/task_badges.py
  modified:
    - backend/app/routers/tasks.py
    - backend/app/__init__.py
decisions:
  - "Kept TaskFieldSeen/exists imports in task_badges.py (needed for org-summary unseen_q)"
  - "Removed orphaned TaskFieldSeen and exists imports from tasks.py after extraction"
  - "Router prefix stays /api/tasks — badges are sub-paths of tasks namespace"
metrics:
  duration_minutes: 12
  completed_date: "2026-04-20"
  tasks_completed: 3
  files_modified: 3
---

# Phase 16 Plan 09: Extract task_badges Summary

**One-liner:** Badge counts, org-summary, and init bootstrap extracted into `task_badges.py` (326 lines) with `_get_visible_user_ids` imported from `task_visibility`.

## What Was Done

- Created `backend/app/routers/task_badges.py` (326 lines) with three endpoints:
  - `GET /api/tasks/badges` — sidebar badge counts (new tasks, changes, chat unread)
  - `GET /api/tasks/org-summary` — per-org task/purchase/unseen-change counters
  - `GET /api/tasks/init` — MyTasksView bootstrap payload (tasks + pending + declines + meta)
- Removed all three endpoint bodies from `tasks.py` (900 lines, down from 1210)
- Registered `task_badges.router` in `backend/app/__init__.py`
- pytest gate: 17/17 passed

## Commits

| Hash | Message |
|------|---------|
| c29bdd0 | feat(16-09): create task_badges.py with badges/org-summary/init endpoints |
| 551b019 | refactor(16-09): remove badges/org-summary/init from tasks.py |
| 82e5929 | refactor(16-09): extract task_badges from tasks |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Cleanup] Removed orphaned imports from tasks.py**
- **Found during:** Task 2
- **Issue:** After removing the three endpoints, `TaskFieldSeen` and `exists` imports in `tasks.py` became unused
- **Fix:** Removed `TaskFieldSeen` from the `task_change` import and `exists` from sqlalchemy imports
- **Files modified:** `backend/app/routers/tasks.py`
- **Commit:** 551b019

## Known Stubs

None.

## Self-Check: PASSED

- `backend/app/routers/task_badges.py`: FOUND (326 lines)
- `backend/app/__init__.py` contains `app.include_router(task_badges.router)`: FOUND
- tasks.py has 0 matches for badges/org-summary/init decorators: CONFIRMED
- pytest 17/17: PASSED
