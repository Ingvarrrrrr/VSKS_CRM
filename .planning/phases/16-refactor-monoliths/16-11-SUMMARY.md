---
phase: 16-refactor-monoliths
plan: 11
subsystem: backend-tasks
tags: [refactor, cross-import, tasks, reports]
dependency_graph:
  requires: [16-07, 16-08, 16-09, 16-10]
  provides: [clean-cross-import, task_reports-module]
  affects: [purchases.py, tasks.py, __init__.py]
tech_stack:
  added: [task_reports.py]
  patterns: [inline-import-extraction, sub-router-registration]
key_files:
  created:
    - backend/app/routers/task_reports.py
  modified:
    - backend/app/routers/purchases.py
    - backend/app/routers/tasks.py
    - backend/app/__init__.py
decisions:
  - "Extract GET /api/tasks/report/by-department to task_reports.py (not a new table — Rule 2 extraction)"
  - "tasks.py at 641 lines (not 500): create_task + update_task contain dense consent/notification logic that cannot be split without architectural change (Rule 4 boundary)"
metrics:
  duration: "15 min"
  completed: "2026-04-19"
  tasks_completed: 3
  files_changed: 4
---

# Phase 16 Plan 11: Cross-Import Fix + tasks.py Report Extraction Summary

**One-liner:** Fix purchases.py stale import of `_enrich_tasks` from tasks.py to task_visibility.py, and extract department report endpoint to slim tasks.py from 730 to 641 lines.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Fix purchases cross-import | 0b75c0c | purchases.py |
| 2 | Extract report + slim tasks.py | 6a0ec6a | tasks.py, task_reports.py, __init__.py |
| 3 | Verification (pytest 17/17) | — | — |

## What Was Done

### Task 1: Cross-Import Fix (REFACTOR-08 primary goal)

`purchases.py` contained a local-scope inline import at line 675:
```python
from app.routers.tasks import _enrich_tasks
```

After Plan 16-07 moved `_enrich_tasks` to `task_visibility.py`, this worked
because `tasks.py` re-imports it. But the dependency graph was polluted:
`purchases → tasks → task_visibility` instead of `purchases → task_visibility`.

Fixed to:
```python
from app.routers.task_visibility import _enrich_tasks
```

Whole-tree verification: `grep -rn "from app.routers.tasks import _enrich_tasks" backend/` → 0 hits.

### Task 2: Department Report Extraction (tasks.py slim)

`GET /api/tasks/report/by-department` (88 lines of logic + 2 imports now unused)
was the only non-CRUD endpoint remaining in tasks.py. Extracted to:

- **New file:** `backend/app/routers/task_reports.py` (116 lines)
- **Registered:** `app.include_router(task_reports.router)` in `__init__.py`
- **Removed from tasks.py:** 90 lines + 2 unused imports (`Query`, `timezone`, `timedelta`)

Result: tasks.py 730 → 641 lines.

## Final Module Line Counts

### Task modules
| Module | Lines | Target | Status |
|--------|-------|--------|--------|
| tasks.py | 641 | ≤500 | OVER — see deviation |
| task_visibility.py | 291 | — | OK |
| task_comments.py | 279 | — | OK |
| task_badges.py | 326 | — | OK |
| task_delegation.py | 251 | — | OK |
| task_reports.py | 116 | NEW | OK |

### Purchase modules
| Module | Lines | Target | Status |
|--------|-------|--------|--------|
| purchases.py | 980 | — | OK |
| purchase_approvals.py | 466 | — | OK |
| purchase_budget.py | 125 | — | OK |
| purchase_events.py | 191 | — | OK |
| purchase_export.py | 478 | — | OK |
| purchase_files.py | 285 | — | OK |
| purchase_items_import.py | 1267 | — | OK |
| purchase_members.py | 341 | — | OK |
| purchase_transitions.py | 264 | — | OK |

## Deviations from Plan

### Deviation 1 — tasks.py at 641, not ≤500

**Target:** D-09 required tasks.py ≤ 500 lines.

**Actual:** 641 lines after report extraction.

**Root cause:** `create_task` (179 lines) and `update_task` (220 lines) contain
dense inline consent/notification/hierarchy logic. All remaining endpoints are:
- `list_tasks` — 78 lines (complex visibility filter)
- `my_tasks` — 22 lines
- `categories` + `departments` — 20 lines
- `create_task` — 179 lines (consent/subordinate/dept/org checks inline)
- `update_task` — 220 lines (same + assignee diff tracking)
- `review_complete` — 40 lines
- `get_task` + `list_subtasks` + `delete_task` — 30 lines
- header/imports — 28 lines

Splitting `create_task` or `update_task` consent logic into a helper module
would require a **new shared service layer** (Rule 4: architectural change).
The plan explicitly states: "If tasks.py can't reach ≤500 without scope creep,
document deviation in SUMMARY. User will decide at verifier stage."

**Recommendation for follow-up:** Extract consent/notification helpers from
`create_task` and `update_task` into `task_consent.py` helper module (no router).
Would reduce tasks.py to ~380 lines. Requires dedicated plan (16-12).

### Auto-fixed Issues

**1. [Rule 2 - Missing] Removed stale unused imports from tasks.py**
- Found during: Task 2 (after report extraction)
- Issue: `Query`, `timezone`, `timedelta` only used by the extracted report endpoint
- Fix: Removed all 3 from import lines
- Files modified: tasks.py
- Commit: 6a0ec6a

## Verification

```
pytest tests/test_routers_mounted.py -q → 17 passed
grep -rn "from app.routers.tasks import _enrich_tasks" backend/ → 0 hits
grep -c "from app.routers.task_visibility import _enrich_tasks" backend/app/routers/purchases.py → 1
wc -l backend/app/routers/tasks.py → 641
```

## Known Stubs

None — all endpoints return real data from database.

## Self-Check: PASSED

- [x] `backend/app/routers/task_reports.py` — FOUND
- [x] `backend/app/routers/tasks.py` — FOUND (641 lines)
- [x] `backend/app/routers/purchases.py` — FOUND (cross-import fixed)
- [x] commit 0b75c0c — cross-import fix
- [x] commit 6a0ec6a — report extraction
- [x] 17/17 pytest passed
