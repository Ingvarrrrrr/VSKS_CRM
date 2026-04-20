---
phase: 13-v3-drag-drop-n
plan: 02
subsystem: backend
tags: [fastapi, sqlalchemy, alembic, pytest, atomic-transaction, wishes, purchases]

# Dependency graph
requires:
  - phase: 13-v3-drag-drop-n plan 01
    provides: Alembic head n1o2p3q4r5s6 (Wave 1 prerequisite)

provides:
  - WishItem.target_column_key VARCHAR(200) NULL (D-04 kanban column persistence)
  - Alembic migration o2p3q4r5s6t7 chaining from n1o2p3q4r5s6
  - PATCH /api/wishes/{wish_id}/items/{item_id} — drag-drop persistence endpoint
  - POST /api/wishes/{wish_id}/approve-distribution — atomic N-purchase creation endpoint
  - WishItemPatch + WishItemOut.target_column_key schemas
  - 5 pytest tests proving atomicity, scope enforcement, read-only gate

affects:
  - 13-05-kanban (frontend uses PATCH and POST endpoints)
  - 13-07-e2e (tests validate approve-distribution contract)
  - purchases table (N rows created per approval)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Atomic FastAPI endpoint: try/except with explicit await db.rollback() on failure"
    - "_resolve_key() fallback chain: target_column_key → product.category → '__uncategorized__'"
    - "Monkeypatch Purchase.__init__ to induce failure on 2nd instantiation for rollback test"
    - "ASGITransport in-process test pattern with real committed DB data"

key-files:
  created:
    - backend/alembic/versions/o2p3q4r5s6t7_add_wish_item_target_column_key.py
    - backend/tests/test_wish_approve_distribution.py
  modified:
    - backend/app/models/wish_item.py
    - backend/app/schemas/wishes.py
    - backend/app/routers/wishes.py
    - backend/tests/conftest.py

key-decisions:
  - "PATCH returns 409 (not 403) for approved wish — indicates conflict with resource state, not authorization"
  - "Cross-wish PATCH returns 404 — item simply does not exist in that wish's scope"
  - "approve-distribution groups by _resolve_key: target_column_key → product.category → '__uncategorized__'"
  - "Explicit db.rollback() in except block ensures atomicity even without SQLAlchemy nested transaction"
  - "product relationship added to WishItem model to enable category resolution without N+1"
  - "Rollback test uses monkeypatch on Purchase.__init__ (2nd call) — proves all-or-nothing behavior"
  - "conftest.py extended minimally: db_session, test_org, test_user, test_admin_user, auth_headers, admin_headers"

# Metrics
duration: 30min
completed: 2026-04-20
---

# Phase 13 Plan 02: Wish Distribution Approve Summary

**Atomic all-or-nothing approve endpoint creating N purchases per kanban column group, PATCH endpoint for drag-drop persistence, and 5 pytest tests proving rollback on induced failure — backend implementation of D-04, D-05, D-06**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-04-20T00:00:00Z
- **Completed:** 2026-04-20
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

### Task 1: Column + Migration + Schema
- Added `target_column_key = Column(String(200), nullable=True)` to `WishItem` model (D-04)
- Added `product` relationship to `WishItem` for category resolution without extra queries
- Created Alembic migration `o2p3q4r5s6t7` chaining from `n1o2p3q4r5s6` (Wave 2 dependency guaranteed)
- Added `target_column_key: Optional[str] = None` to `WishItemOut` schema
- Added `WishItemPatch` schema for PATCH payload

### Task 2: Endpoints
- `PATCH /{wish_id}/items/{item_id}` — persists drag-drop result, returns 409 on approved wish, 404 on cross-wish access
- `POST /{wish_id}/approve-distribution` — groups items by `_resolve_key()` (target_column_key → product.category → '__uncategorized__'), creates N purchases (status='wishes') atomically with explicit rollback on any failure, creates assignment chat rooms, marks wish approved
- Both endpoints added to existing `backend/app/routers/wishes.py` without new router file

### Task 3: Pytest Suite
- `test_approve_distribution_creates_n_purchases` — happy path: 3 groups → 3 purchases, wish.status='approved'
- `test_double_approve_returns_400` — idempotency guard: second call returns 400
- `test_patch_item_blocked_when_approved` — D-05 read-only gate: 409 on approved wish PATCH
- `test_patch_item_wrong_wish_returns_404` — D-04 scope: 404 when item belongs to different wish
- `test_approve_distribution_rollback_on_failure` — D-05 atomicity: monkeypatch raises on 2nd Purchase() call → HTTP 500, zero purchases in DB, wish.status unchanged
- Extended `conftest.py` with 6 new fixtures (db_session, test_org, test_user, test_admin_user, auth_headers, admin_headers)

## Task Commits

1. **Task 1: Column + migration + schema** — `4d0504a` (feat)
2. **Task 2: Endpoints** — `ce23b53` (feat)
3. **Task 3: Tests** — `1114be2` (test)

## Files Created/Modified

- `backend/alembic/versions/o2p3q4r5s6t7_add_wish_item_target_column_key.py` — migration: add VARCHAR(200) NULL column, reversible downgrade
- `backend/app/models/wish_item.py` — target_column_key column + product relationship
- `backend/app/schemas/wishes.py` — WishItemOut.target_column_key field + WishItemPatch class
- `backend/app/routers/wishes.py` — PATCH /items/{item_id} + POST /approve-distribution + 3 new imports
- `backend/tests/test_wish_approve_distribution.py` — 5 full-body async tests
- `backend/tests/conftest.py` — 6 new fixtures for DB-backed testing

## Decisions Made

- **409 vs 403 for approved wish edit:** 409 Conflict chosen — the resource state (approved) conflicts with the operation, not the user's authorization
- **Cross-wish PATCH → 404:** Item simply does not exist in the specified wish's scope; no leaking of resource existence
- **Explicit db.rollback():** Used `try/except` with `await db.rollback()` rather than nested savepoints — simpler and correct for this use case
- **product relationship on WishItem:** Added directly to model to avoid N+1 and enable efficient selectinload in approve-distribution
- **conftest extended minimally:** Only added fixtures required by the new test file; existing `client` fixture untouched

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing relationship] Added `product` relationship to WishItem**
- **Found during:** Task 1 implementation
- **Issue:** Plan's `_resolve_key()` accesses `it.product.category` but WishItem had no `product` relationship defined
- **Fix:** Added `product = relationship("Product", foreign_keys=[product_id])` to WishItem model
- **Files modified:** `backend/app/models/wish_item.py`
- **Commit:** `4d0504a`

## Known Stubs

None — all endpoint logic and test assertions are fully implemented.

## Self-Check: PASSED

All created files exist:
- FOUND: `backend/app/models/wish_item.py`
- FOUND: `backend/alembic/versions/o2p3q4r5s6t7_add_wish_item_target_column_key.py`
- FOUND: `backend/app/routers/wishes.py`
- FOUND: `backend/app/schemas/wishes.py`
- FOUND: `backend/tests/test_wish_approve_distribution.py`

All commits verified:
- `4d0504a` feat(13-02): add WishItem.target_column_key column + migration + schema
- `ce23b53` feat(13-02): PATCH /items/{item_id} + POST /approve-distribution endpoints
- `1114be2` test(13-02): 5 pytest tests for approve-distribution atomicity + PATCH scope

Success criteria:
- [x] `wish_items.target_column_key` column added, nullable
- [x] Migration `o2p3q4r5s6t7` with `down_revision='n1o2p3q4r5s6'`
- [x] PATCH and POST endpoints in wishes.py
- [x] WishItemPatch + WishItemOut.target_column_key in schemas
- [x] 5 non-stub async tests with rollback monkeypatch
- [x] `grep -cE "^\s*(pass|\.\.\.)\s*$"` returns 0
