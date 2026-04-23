---
phase: 17
plan: "02"
subsystem: backend-tests
tags: [testing, permissions, tdd, wave-0, playwright]
dependency_graph:
  requires: []
  provides:
    - backend/tests/conftest.py (phase-17 fixtures)
    - backend/tests/test_permission_migration.py
    - backend/tests/test_require_tab.py
    - backend/tests/test_users_me_permissions.py
    - backend/tests/test_self_lockout.py
    - backend/tests/test_superadmin_visibility.py
    - backend/tests/test_publication_requires_action.py
    - e2e/20-permissions.spec.ts
  affects:
    - Plans 17-03..17-09 (all reference these test files via automated verify)
tech_stack:
  added: []
  patterns:
    - pytest_asyncio fixtures with deferred imports (RED-safe)
    - Parameterized factory fixtures (make_user, make_role_permission, make_override)
    - Playwright test.skip global descriptor for pending frontend plans
key_files:
  created:
    - backend/tests/test_permission_migration.py
    - backend/tests/test_require_tab.py
    - backend/tests/test_users_me_permissions.py
    - backend/tests/test_self_lockout.py
    - backend/tests/test_superadmin_visibility.py
    - backend/tests/test_publication_requires_action.py
    - e2e/20-permissions.spec.ts
  modified:
    - backend/tests/conftest.py
decisions:
  - "Deferred imports inside fixtures (from app.models.permission import ...) prevent RED-state collection errors while 17-01 models are not yet applied to DB"
  - "make_user uses hasattr(User, k) filtering to safely handle can_publish column absence until 17-01 migration runs"
  - "make_role_permission uses yield (generator fixture) for future cleanup hooks; make_override uses return (simpler — no cleanup needed)"
  - "e2e/20-permissions.spec.ts uses test.skip global descriptor — all 3 tests skipped until Plans 17-06/07/08 land frontend"
  - "test_publication_requires_action.py uses /app/app/routers/publications.py path (docker volume mount: backend/app → /app/app)"
metrics:
  duration: "~10 minutes"
  completed_date: "2026-04-23"
  tasks_completed: 2
  tasks_total: 2
  files_created: 7
  files_modified: 1
---

# Phase 17 Plan 02: Wave 0 Validation Scaffolding Summary

Wave 0 test infrastructure for Phase 17 permission system — 6 pytest modules + Playwright E2E scaffold + 6 conftest fixtures. All backend tests are in RED state by design (models/endpoints not yet implemented by Plans 17-03..17-09).

## What Was Built

### Task 1: conftest.py Permission Fixtures

Extended `backend/tests/conftest.py` with 6 new fixtures (existing fixtures untouched):

| Fixture | Type | Purpose |
|---------|------|---------|
| `superadmin_user` | `async` | Creates User with role=superadmin in test_org |
| `superadmin_headers` | sync | JWT headers for superadmin_user |
| `user_org_access` | `async` | Ensures UserOrgAccess row exists for test_user/test_org |
| `make_user` | `async` factory | Parameterized: `make_user(role, org_id, can_publish)` |
| `make_role_permission` | `async` generator | Creates RolePermission rows; `yield` for cleanup hook |
| `make_override` | `async` | Creates UserOrgPermissionOverride rows |

All imports deferred inside fixtures (`from app.models.permission import ...`) to prevent collection errors while Plan 17-01 models exist on disk but DB migration hasn't run yet.

### Task 2: 6 Backend Test Files + E2E Spec

All files in RED state — they test behavior that Plans 17-03..17-09 implement:

| File | Plan Target | Requirement | Key Tests |
|------|------------|-------------|-----------|
| `test_permission_migration.py` | 17-01 | D-05 seed | seed_23_tabs, seed_7_actions, seed_idempotent |
| `test_require_tab.py` | 17-03 | D-01b guards | require_tab_403, superadmin_bypass, require_action_403 |
| `test_users_me_permissions.py` | 17-03 | D-08 /users/me | me_returns_permissions_object, override_flips_bit |
| `test_self_lockout.py` | 17-05 | D-05.2 lockout | admin_cannot_revoke_own_admin_roles |
| `test_superadmin_visibility.py` | 17-05 | D-09 visibility | list_users_excludes_superadmin_for_non_superadmin |
| `test_publication_requires_action.py` | 17-04 | D-06 can_publish | publication_403_without_override, no_inline_can_publish |
| `e2e/20-permissions.spec.ts` | 17-06/07/08 | D-01a/03/04 | 3 tests, all globally skipped |

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: conftest fixtures | `a4f2357` | backend/tests/conftest.py |
| Task 2: test files + E2E | `06cb1d4` | 6 backend test files + e2e/20-permissions.spec.ts |

## Self-Check: PASSED

Files verified to exist:
- `backend/tests/conftest.py` — FOUND (superadmin_user, superadmin_headers, user_org_access, make_user, make_role_permission, make_override all present)
- `backend/tests/test_permission_migration.py` — FOUND (test_seed_idempotent, test_seed_23_tabs)
- `backend/tests/test_require_tab.py` — FOUND (test_require_tab_403_when_not_in_effective, test_superadmin_bypasses_all_tabs)
- `backend/tests/test_users_me_permissions.py` — FOUND (test_me_returns_permissions_object)
- `backend/tests/test_self_lockout.py` — FOUND (test_admin_cannot_revoke_own_admin_roles)
- `backend/tests/test_superadmin_visibility.py` — FOUND (test_list_users_excludes_superadmin_for_non_superadmin)
- `backend/tests/test_publication_requires_action.py` — FOUND (test_publication_requires_action_403_without_override, test_publications_router_has_no_inline_can_publish)
- `e2e/20-permissions.spec.ts` — FOUND (test.describe('Permissions system'))

Commits verified:
- `a4f2357` — FOUND (test(17-02): extend conftest.py)
- `06cb1d4` — FOUND (test(17-02): create 6 backend test modules + E2E spec)

Python syntax validated: all 7 Python files pass `ast.parse()` check.
