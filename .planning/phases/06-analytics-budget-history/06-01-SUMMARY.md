---
phase: 06-analytics-budget-history
plan: 01
subsystem: database
tags: [sqlalchemy, postgres, audit-log, budget, purchase, subsidy]

# Dependency graph
requires:
  - phase: 01-purchase-form
    provides: Purchase model with planned_total_price and subsidy_id fields
  - phase: 02-cascading-feo
    provides: Subsidy model with budget field
provides:
  - BudgetHistory SQLAlchemy model (budget_history table)
  - Write hooks in create_purchase, update_purchase, update_subsidy
  - budget_history table populated on every relevant value change
affects: [06-analytics-budget-history, future history API plans]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inline import pattern: `from app.models.X import X as _X` inside route function for late-binding"
    - "Capture-before-mutate: read old value before setattr loop, compare after, write audit row"

key-files:
  created:
    - backend/app/models/budget_history.py
  modified:
    - backend/app/models/__init__.py
    - backend/app/routers/purchases.py
    - backend/app/routers/subsidies.py

key-decisions:
  - "Old budget_history table (mismatched schema: old_budget/new_budget/user_id columns, 1 orphaned test row) dropped and recreated with new schema. Old row had no user_id and was clearly test data — not production-critical."
  - "Inline import used for BudgetHistory inside route functions to avoid circular import risk"
  - "create_purchase hook uses existing db.flush() (already present at line 628) so p.id is populated before writing history row"

patterns-established:
  - "Audit row pattern: capture old value → run mutation → compare → db.add(AuditModel(...)) before await db.commit()"

requirements-completed: [BUDGET-07]

# Metrics
duration: 15min
completed: 2026-04-04
---

# Phase 6 Plan 01: BudgetHistory Model + Write Hooks Summary

**BudgetHistory SQLAlchemy model created and registered; write hooks added to create_purchase, update_purchase, and update_subsidy so every planned_total_price and subsidy budget change produces an audit row**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-04T07:04:00Z
- **Completed:** 2026-04-04T07:19:11Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Created `backend/app/models/budget_history.py` with BudgetHistory model (subsidy_id, purchase_id, entity_type, old_value, new_value, changed_by_id, changed_by_name, reason, changed_at)
- Registered BudgetHistory in `models/__init__.py` so `create_all` builds the table on startup
- Added write hooks in `create_purchase` (old_value=None, uses existing db.flush() for p.id), `update_purchase` (captures old_planned_total_price before setattr loop, fires only when value changes), and `update_subsidy` (captures old_budget before setattr loop, tracks `budget` only — not `calculated_budget`)
- Old mismatched budget_history table dropped; new correct schema created via init_db restart; Docker container starts cleanly

## Task Commits

1. **Task 1: Create BudgetHistory model and register it** - `053b44d` (feat)
2. **Task 2: Add write hooks in update_purchase, create_purchase, and update_subsidy** - `edaf2ed` (feat)

**Plan metadata:** (final doc commit — see below)

## Files Created/Modified
- `backend/app/models/budget_history.py` - BudgetHistory SQLAlchemy ORM model with 10 columns
- `backend/app/models/__init__.py` - Added BudgetHistory import for create_all registration
- `backend/app/routers/purchases.py` - Added old_planned_total_price capture + 2 write hooks (create, update)
- `backend/app/routers/subsidies.py` - Added old_budget capture + subsidy budget write hook

## Decisions Made
- Old `budget_history` table had mismatched schema (columns: old_budget, new_budget, user_id) with 1 orphaned test row (no user_id, clearly not production data). Dropped and recreated — plan explicitly allowed this for mismatched empty/near-empty tables.
- Used inline imports (`from app.models.budget_history import BudgetHistory as _BH`) inside route functions to avoid potential circular import issues at module load time.
- `create_purchase` hook placed after existing `await db.flush()` at line 628 which already populates `p.id` — no extra flush needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Old budget_history table had mismatched schema, dropped and recreated**
- **Found during:** Task 1 (verification after model creation)
- **Issue:** Existing table had columns `old_budget`, `new_budget`, `user_id`, `created_at` — completely different from the new model's `old_value`, `new_value`, `changed_by_id`, `changed_by_name`, `entity_type`, `purchase_id`, `changed_at`
- **Fix:** Checked table contents (1 orphaned test row, no user_id), dropped table via `docker exec psql`, restarted backend container to recreate with correct schema
- **Files modified:** No code changes — database operation only
- **Verification:** `\d budget_history` confirms new schema with all 10 columns and correct FKs
- **Committed in:** edaf2ed (part of Task 2 commit message)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug: schema mismatch)
**Impact on plan:** Required to unblock the feature. Old test row had no production value.

## Issues Encountered
- None beyond the schema mismatch handled above.

## User Setup Required
None - no external service configuration required. Table is auto-created on backend container restart.

## Next Phase Readiness
- `budget_history` table is live and being populated on every planned_total_price and subsidy budget change
- Ready for Phase 06-02: history API endpoint (`GET /api/subsidies/{id}/history`)
- Ready for Phase 06-03: budget history timeline UI in subsidy detail view

---
*Phase: 06-analytics-budget-history*
*Completed: 2026-04-04*
