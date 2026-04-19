---
phase: 16-refactor-monoliths
plan: 01
subsystem: testing
tags: [pytest, pytest-asyncio, httpx, ASGITransport, smoke-tests, fastapi]

requires:
  - phase: 15-purchase-items-editor
    provides: stable endpoint surface that this harness validates

provides:
  - pytest infrastructure in backend container (pytest==7.4.4, pytest-asyncio==0.23.3)
  - backend/tests/conftest.py with ASGITransport-based AsyncClient fixture
  - backend/tests/test_routers_mounted.py — 17-test parametrized smoke harness (9 parametrized + 8 named)
  - Baseline green: 17/17 pass pre-refactor in 8.26s

affects: [16-02, 16-03, 16-04, 16-05, 16-06, 16-07, 16-08, 16-09, 16-10]

tech-stack:
  added: [pytest==7.4.4, pytest-asyncio==0.23.3]
  patterns:
    - ASGITransport fixture pattern for in-process FastAPI testing (no network, no DB teardown)
    - 401/403 accepted as proof of router mount (auth-gated endpoints still prove router IS mounted)
    - Named test functions for per-extract verify commands in future plans

key-files:
  created:
    - backend/pytest.ini
    - backend/tests/__init__.py
    - backend/tests/conftest.py
    - backend/tests/test_routers_mounted.py
  modified:
    - backend/requirements.txt

key-decisions:
  - "httpx 0.27.0 already present — kept existing version, did not pin to 0.26.0"
  - "ASGITransport (in-process) chosen over real HTTP to avoid port conflicts and keep < 10s"
  - "401/403 accepted as valid proof of router mount — avoids need for test JWT in Wave 0"

patterns-established:
  - "Smoke gate pattern: parametrized MOUNT_PROBES list + named per-extract tests for plans 16-02..16-10"
  - "App import deferred in conftest.py to avoid import-time side effects"

requirements-completed: [REFACTOR-06]

duration: 12min
completed: 2026-04-19
---

# Phase 16 Plan 01: pytest infrastructure + router-mount smoke harness (17/17 baseline green)

**ASGITransport-based pytest harness for FastAPI with 17-test smoke suite confirming all major routers mounted — 8.26s baseline pre-refactor, gates every subsequent extraction commit**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-04-19T22:40:00Z
- **Completed:** 2026-04-19T22:52:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- pytest==7.4.4 + pytest-asyncio==0.23.3 added to requirements.txt and installed in running container
- conftest.py: ASGITransport fixture lets tests hit FastAPI in-process — no port, no network, no DB teardown needed
- test_routers_mounted.py: 9 parametrized MOUNT_PROBES + 8 named tests; 17/17 PASS in 8.26s against live pre-refactor codebase
- Baseline captured — any future router-mount regression caught in < 10s

## Task Commits

1. **Task 1: Install pytest deps + config** - `891106d` (test)
2. **Task 2: conftest.py with AsyncClient fixture** - `fad53a3` (test)
3. **Task 3: test_routers_mounted.py baseline smoke** - `1bd1912` (test)

## Files Created/Modified

- `backend/requirements.txt` — added pytest==7.4.4, pytest-asyncio==0.23.3 (httpx 0.27.0 kept)
- `backend/pytest.ini` — asyncio_mode=auto, testpaths=tests
- `backend/tests/__init__.py` — pytest package marker (empty)
- `backend/tests/conftest.py` — AsyncClient fixture via ASGITransport(app=app)
- `backend/tests/test_routers_mounted.py` — 17-test smoke harness

## Decisions Made

- httpx 0.27.0 was already present in requirements.txt — kept existing version (plan specified 0.26.0 only as minimum)
- ASGITransport pattern: app import deferred inside fixture body (`from app import app`) to avoid import-time side effects at collection phase
- 401/403 accepted as valid: proves router is mounted without needing a test JWT in Wave 0

## Deviations from Plan

None - plan executed exactly as written. httpx version kept at existing 0.27.0 (newer than plan's 0.26.0) — not a deviation, an accepted upgrade.

## Issues Encountered

None. All 17 tests green on first run.

## Baseline Test Output

```
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-7.4.4, pluggy-1.6.0
asyncio: mode=Mode.AUTO
collected 17 items

tests/test_routers_mounted.py::test_router_mounted[/api/purchases/-GET] PASSED
tests/test_routers_mounted.py::test_router_mounted[/api/purchases/export/columns-GET] PASSED
tests/test_routers_mounted.py::test_router_mounted[/api/purchases/export/excel-GET] PASSED
tests/test_routers_mounted.py::test_router_mounted[/api/purchases/items/import/template-GET] PASSED
tests/test_routers_mounted.py::test_router_mounted[/api/tasks/-GET] PASSED
tests/test_routers_mounted.py::test_router_mounted[/api/tasks/badges-GET] PASSED
tests/test_routers_mounted.py::test_router_mounted[/api/tasks/org-summary-GET] PASSED
tests/test_routers_mounted.py::test_router_mounted[/api/tasks/pending-consent-GET] PASSED
tests/test_routers_mounted.py::test_router_mounted[/api/tasks/consent-declines-GET] PASSED
tests/test_routers_mounted.py::test_export_mount PASSED
tests/test_routers_mounted.py::test_items_import_mount PASSED
tests/test_routers_mounted.py::test_members_mount PASSED
tests/test_routers_mounted.py::test_transitions_mount PASSED
tests/test_routers_mounted.py::test_visibility_mount PASSED
tests/test_routers_mounted.py::test_badges_mount PASSED
tests/test_routers_mounted.py::test_delegation_mount PASSED
tests/test_routers_mounted.py::test_comments_mount PASSED
======================= 17 passed, 10 warnings in 8.26s ========================
```

## Known Stubs

None.

## Next Phase Readiness

Plans 16-02..16-10 can now use `docker exec vsks_crm-backend-1 sh -c "cd /app && pytest tests/test_routers_mounted.py -q"` as a fast gate after each extraction commit. Named per-extract test functions (test_export_mount, test_items_import_mount, etc.) available for targeted verification.

---
*Phase: 16-refactor-monoliths*
*Completed: 2026-04-19*
