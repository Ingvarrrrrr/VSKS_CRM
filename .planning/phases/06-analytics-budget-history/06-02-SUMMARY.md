---
phase: 06-analytics-budget-history
plan: 02
subsystem: api
tags: [fastapi, pydantic, pagination, audit-log, budget, history]

# Dependency graph
requires:
  - phase: 06-01
    provides: BudgetHistory SQLAlchemy model (budget_history table)
provides:
  - BudgetHistoryItemOut Pydantic schema in schemas.py
  - GET /api/subsidies/{id}/history paginated endpoint in subsidies.py
affects: [06-analytics-budget-history, 06-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Paginated list endpoint pattern: count subquery + offset/limit rows + {total, items} response"
    - "Inline import inside route function to avoid circular import: from app.models.X import X as _X"

key-files:
  created: []
  modified:
    - backend/app/schemas/schemas.py
    - backend/app/routers/subsidies.py

key-decisions:
  - "old_value/new_value typed as Optional[float] in BudgetHistoryItemOut (not Decimal) for clean JSON serialisation"
  - "/{subsidy_id}/history route appended after all existing routes to avoid FastAPI path conflict with /{subsidy_id} integer route"
  - "Query imported on the fastapi import line (not just used as default) per plan requirement"

requirements-completed: [BUDGET-08]

# Metrics
duration: 5min
completed: 2026-04-04
---

# Phase 6 Plan 02: Budget History API Endpoint Summary

**BudgetHistoryItemOut Pydantic schema added and GET /api/subsidies/{id}/history paginated endpoint implemented — exposes audit log rows with descending chronological order and offset/limit pagination**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-04T07:22:24Z
- **Completed:** 2026-04-04T07:27:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `BudgetHistoryItemOut` class to `schemas.py` with 8 fields: id, entity_type, purchase_id, old_value (Optional[float]), new_value (Optional[float]), changed_by_name, reason, changed_at (Optional[datetime])
- Added `Query` to fastapi imports in `subsidies.py`
- Appended `get_budget_history` route at end of `subsidies.py`: selects from `budget_history` where `subsidy_id == id`, orders by `changed_at DESC`, returns `{total: N, items: [...]}`
- Pagination via `offset` (default 0) and `limit` (default 50, max 200) query params using count subquery pattern from contractors.py

## Task Commits

1. **Task 1: Add BudgetHistoryItemOut schema** - `ed5310f` (feat)
2. **Task 2: Add GET /{subsidy_id}/history endpoint** - `d0fd3c4` (feat)

## Files Created/Modified

- `backend/app/schemas/schemas.py` - Appended BudgetHistoryItemOut class with 8 fields (14 lines added)
- `backend/app/routers/subsidies.py` - Added Query to import line + appended get_budget_history function (42 lines added)

## Decisions Made

- `old_value` and `new_value` typed as `Optional[float]` in the Pydantic schema (not `Decimal`) because the endpoint serialises them inline as `float(r.old_value)` — avoids Decimal serialisation issues in JSON responses.
- Route appended after all existing routes per plan guidance — FastAPI matches in order; appending `/{subsidy_id}/history` after `/{subsidy_id}` works because "history" is a literal string segment that won't be matched as an integer.
- `Query` added to the `from fastapi import ...` line at module top (not just used as a default value inline) as required by success criteria.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

Docker image rebuild required for the endpoint to be live:
```bash
docker compose build backend && docker compose up -d backend
```
After rebuild: `curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/subsidies/7/history` returns `{"total": N, "items": [...]}`.

## Next Phase Readiness

- API endpoint `GET /api/subsidies/{id}/history` is ready for consumption
- Ready for Phase 06-03: budget history timeline UI dialog in subsidy detail view

---
*Phase: 06-analytics-budget-history*
*Completed: 2026-04-04*
