---
phase: 16
slug: refactor-monoliths
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-19
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution of Refactor Monoliths. Goal: ZERO functional regression. Validation is the only safety net since nothing new is built.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Frontend framework** | Playwright 1.x (already installed, e2e/ directory) |
| **Backend framework** | **pytest 7.x + httpx — NOT installed yet. Wave 0 of purchases.py plan MUST bootstrap.** |
| **Frontend config file** | `playwright.config.ts` |
| **Backend config file** | `backend/tests/conftest.py` — to be created in Wave 0 |
| **Quick run command (E2E smoke subset)** | `BASE_URL=http://85.239.53.155 npx playwright test e2e/01-login.spec.ts e2e/18-purchase-items-editor.spec.ts` |
| **Full E2E command** | `BASE_URL=http://85.239.53.155 npx playwright test` |
| **Backend smoke command** | `cd backend && pytest tests/test_routers_mounted.py -q` |
| **Estimated runtimes** | Smoke subset ~30s, full E2E ~5-8 min on deploy, backend smoke ~10s |

---

## Sampling Rate

- **After every task commit (= every atomic "extract X from Y"):** Run `backend smoke` (10s) + `quick E2E subset` (30s) = **~40s feedback latency**
- **After every plan wave (= all extractions for purchases.py done, or all for tasks.py done, or MyTasksView split):** Run `full E2E` (~5-8 min)
- **Before `/gsd:verify-work` (phase end):** Full E2E MUST be green + manual visual diff on MyTasksView
- **Max feedback latency per commit:** 60 seconds (includes pytest + playwright smoke)

---

## Per-Task Verification Map

_Planner will populate this table with exact commit-level verification after plan creation. Stub:_

| Task ID | Plan | Wave | Purpose | Test Type | Automated Command | File Exists | Status |
|---------|------|------|---------|-----------|-------------------|-------------|--------|
| 16-01-00 | 01 | 0 | Bootstrap pytest + routers smoke harness | unit | `cd backend && pytest tests/test_routers_mounted.py -q` | ❌ W0 | ⬜ pending |
| 16-01-01 | 01 | 1 | Extract `purchase_export.py` | integration | `curl -sI /api/purchases/export/excel` + `pytest tests/test_routers_mounted.py::test_export_mount -q` | ❌ W0 | ⬜ pending |
| 16-01-02 | 01 | 1 | Extract `purchase_items_import.py` | integration | `pytest -k items_import_mount` + E2E smoke | ❌ W0 | ⬜ pending |
| 16-01-03 | 01 | 1 | Extract `purchase_budget.py` (helper module, no router) | unit import | `python -c "from app.routers.purchase_budget import _check_budget"` | ❌ W0 | ⬜ pending |
| 16-01-04 | 01 | 2 | Extract `purchase_members.py` | integration | `pytest -k members_mount` | ❌ W0 | ⬜ pending |
| 16-01-05 | 01 | 2 | Extract `purchase_transitions.py` | integration | `pytest -k transitions_mount` + `BASE_URL=... npx playwright test e2e/02-purchases.spec.ts` | ❌ W0 | ⬜ pending |
| 16-02-00..05 | 02 | 0-2 | tasks.py extractions (visibility, comments, badges, delegation) | integration | parametrized `pytest tests/test_routers_mounted.py` per new router | ❌ W0 | ⬜ pending |
| 16-03-00..05 | 03 | 0-2 | MyTasksView.vue → 5 components | E2E | `BASE_URL=... npx playwright test e2e/22-my-tasks.spec.ts` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · W0: blocked by Wave 0*

---

## Wave 0 Requirements

These MUST be done in Wave 0 of Plan 16-01 before any extraction:

- [ ] `backend/tests/__init__.py` — marker for pytest
- [ ] `backend/tests/conftest.py` — shared fixtures: `async def client()` wrapping httpx.AsyncClient on FastAPI app, `auth_token` fixture, `db_session` rollback fixture
- [ ] `backend/tests/test_routers_mounted.py` — parametrized mount test: for each router name, assert `/openapi.json` lists it and that a happy-path endpoint returns 200 or 401 (auth-required is fine — 500 is NOT)
- [ ] `backend/requirements-dev.txt` OR update `backend/requirements.txt` with `pytest`, `pytest-asyncio`, `httpx` (if not already present)
- [ ] Install in backend container OR document `docker exec vsks_crm-backend-1 pip install pytest pytest-asyncio httpx`
- [ ] Baseline run: `pytest tests/test_routers_mounted.py` must pass for CURRENT (pre-refactor) state before any extraction starts. If any currently-mounted router 500s on happy-path → **BLOCKER — fix before phase proceeds.**

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| MyTasksView visual identity | D-28 | No frontend visual-regression framework in project. Pixel-diff not automated. | Before Plan 16-03 starts: take screenshot of `/my-tasks` at `BASE_URL`. After Plan 16-03 done: screenshot again. Compare side-by-side: layout, spacing, colors, interactive state (tab switch, org selector, kanban drag) MUST be identical. Document in `16-UAT.md`. |
| Telegram/chat integration post-members-extract | D-06, D-12 | Requires live Telegram bot + chat-room auto-creation on assignment | Assign a purchase to a user, verify chat room auto-created (check `/api/chat/rooms`), send a Telegram message from bot, verify reply flows back. Run manually on deploy after Plan 16-01 Wave 2 (purchase_members extract). |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies documented
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify (ENFORCED by per-task `pytest` or E2E command)
- [ ] Wave 0 bootstrap covers all backend routers (parametrized mount test)
- [ ] No watch-mode flags (all runs must be one-shot, exit-code-driven)
- [ ] Feedback latency < 60s per commit
- [ ] `nyquist_compliant: true` set in frontmatter after Wave 0 completes green baseline

**Approval:** pending — awaits Plan 16-01 Wave 0 green baseline
