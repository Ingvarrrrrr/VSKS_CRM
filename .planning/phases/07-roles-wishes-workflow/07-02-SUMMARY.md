---
phase: 07-roles-wishes-workflow
plan: 02
subsystem: api
tags: [fastapi, sqlalchemy, wishes, purchases, roles, org-isolation]

# Dependency graph
requires:
  - phase: 07-01
    provides: Wish model, WishCreate/Update/Reject/Convert/Out schemas, migration applied, GET /api/wishes endpoint scaffold

provides:
  - POST /api/wishes: create wish (all roles, status=draft, org isolation)
  - PUT /api/wishes/{id}: update draft wish (creator only)
  - POST /api/wishes/{id}/submit: draft -> submitted (creator only)
  - POST /api/wishes/{id}/approve: submitted -> approved (MANAGER_ROLES, org check)
  - POST /api/wishes/{id}/reject: submitted -> rejected with rejection_reason (MANAGER_ROLES, D-08)
  - POST /api/wishes/{id}/convert: approved -> converted + inline Purchase creation (ADMIN_ROLES, D-23)
  - DELETE /api/wishes/{id}: delete draft (creator only, 204)
  - Employee purchase list strictly filtered to assigned_user_id = current_user.id (D-13)

affects: [frontend-wishes-views, 07-03, employee-purchase-list]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - _load_wish() helper for consistent selectinload(creator/approver) on every endpoint
    - _enrich() helper converts Wish ORM to WishOut with computed name fields
    - Inline db.flush() before reading p.id in convert endpoint (same pattern as create_purchase)
    - Employee vs manager split branching in list_purchases() for D-13 compliance

key-files:
  created: []
  modified:
    - backend/app/routers/wishes.py
    - backend/app/routers/purchases.py

key-decisions:
  - "Employee purchase filter uses q.where(Purchase.assigned_user_id == current_user.id) with no NULL fallback — D-13 strict compliance"
  - "convert_wish creates Purchase inline via db.flush() pattern (not HTTP call to create_purchase) — avoids budget check side-effects on wish-origin purchases"
  - "selectinload used instead of lazy='joined' on individual endpoint loads for explicit N+1 prevention"

patterns-established:
  - "_load_wish(): shared helper that raises 404 and eagerly loads relationships"
  - "Status gate pattern: check wish.status first, then org isolation, then mutate"

requirements-completed: [WISHES-02, WISHES-03, WISHES-04, WISHES-05, ROLES-03, ROLES-06]

# Metrics
duration: 15min
completed: 2026-04-05
---

# Phase 7 Plan 02: Wishes API + Employee Purchase Filter Summary

**8-endpoint wishes lifecycle (draft/submitted/approved/rejected/converted) with role-gated transitions and inline Purchase creation; employee purchase list strictly filtered to executor-only per D-13**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-05T20:35:00Z
- **Completed:** 2026-04-05T20:50:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Full wishes CRUD (7 endpoints + existing list = 8 total) with correct role enforcement: employee creates/submits, manager approves/rejects, org_admin converts
- Rejection stores `rejection_reason` in DB (D-08 requirement)
- Convert endpoint creates Purchase inline using `db.flush()` pattern — no HTTP call to `create_purchase`, avoids budget check side-effects
- Employee purchase list split from manager: now uses single `q.where(Purchase.assigned_user_id == current_user.id)` with no NULL or PurchaseMember fallback (D-13)

## Task Commits

1. **Task 1: Implement full wishes CRUD + transition endpoints** - `6455a74` (feat)
2. **Task 2: Add employee-only purchase filter per D-13** - `d07dac4` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `backend/app/routers/wishes.py` - Full implementation: create, update, submit, approve, reject, convert, delete endpoints with org isolation and role gating
- `backend/app/routers/purchases.py` - Employee visibility split: `if current_user.role == 'employee': q.where(assigned_user_id == current_user.id)` replaces combined block

## Decisions Made

- `convert_wish` creates Purchase inline (not via HTTP) to avoid triggering budget checks intended for manually created purchases
- `selectinload()` used explicitly in `_load_wish()` rather than relying on model-level `lazy="joined"` — more explicit and avoids surprises with async session
- Employee branch has zero OR conditions — D-13 states "only purchases where they are the executor", so NULL and PurchaseMember fallbacks are deliberately excluded

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Self-Check: PASSED

All files confirmed present, both commits verified in git log.

## Next Phase Readiness

- All wishes lifecycle transitions fully operational; ready for frontend "Мои заявки" (employee) and "Заявки сотрудников" (manager) views
- Employee purchase list now correctly scoped — no further backend changes needed for D-13

---
*Phase: 07-roles-wishes-workflow*
*Completed: 2026-04-05*
