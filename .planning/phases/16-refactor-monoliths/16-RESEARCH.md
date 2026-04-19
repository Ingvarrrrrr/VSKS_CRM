# Phase 16: Refactor Monoliths — Research

**Researched:** 2026-04-19
**Domain:** FastAPI router decomposition + Vue 3 component extraction
**Confidence:** HIGH — based on direct code inspection of all three target files

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Backend first (purchases.py → tasks.py), frontend last.
- D-02: Within each monolith, extract isolated helpers before central CRUD.
- D-03..D-08: purchases.py → 6 modules: purchases (CRUD), purchase_transitions, purchase_budget, purchase_members, purchase_export, purchase_items_import.
- D-09..D-13: tasks.py → 5 modules: tasks (CRUD), task_visibility, task_badges, task_delegation, task_comments.
- D-14..D-18: MyTasksView.vue → 1 orchestrator + 5 co-located components under frontend/src/components/my-tasks/.
- D-19: Shared helpers stay in originating module; others import them.
- D-20: `_purchase_to_full`, `_item_to_out` → in purchases.py.
- D-21: `_get_visible_user_ids` → in task_visibility.py.
- D-22: All HTTP URLs FROZEN.
- D-23: Response schemas FROZEN.
- D-24: All new routers mount in backend/app/__init__.py with same prefix as split-source.
- D-25: Each commit = "extract X from Y", atomic, build-green.
- D-26: Primary gate = all E2E 67+3 pass before/after each commit-extract.
- D-27: 1 smoke integration test per new router-module in backend/tests/test_routers_mounted.py.
- D-28: npm run build zero-warn + manual visual snapshot of MyTasksView.

### Claude's Discretion
- Internal names for private helpers (_foo vs _bar)
- Extraction order within each monolith
- TasksTable.vue vs TasksKanban.vue: one component with :mode prop vs two separate
- Need for backend/app/routers/_shared.py for pure utility formatters

### Deferred Ideas (OUT OF SCOPE)
- backend/app/services/ business-layer
- Unit tests for extracted helpers
- Cleanup of .backup.vue, dead view files
- localStorage unification (auth_token vs access_token)
- OrdersView.vue, CreateOrderView.vue decomposition
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REFACTOR-01 | purchases.py → 6 modules ≤800 lines each | Extraction order + dependency graph documented below |
| REFACTOR-02 | tasks.py → 5 modules ≤800 lines each | Cross-module deps and import graph documented below |
| REFACTOR-03 | MyTasksView.vue → orchestrator + 5 components | State ownership map and props/emits pattern documented |
| REFACTOR-04 | All HTTP URLs preserved unchanged | D-22 + route ordering rules for shared prefix documented |
| REFACTOR-05 | E2E 67+3 pass before and after each atomic commit | Subset list for fast gate, full gate command documented |
| REFACTOR-06 | 1 smoke integration test per new router | pytest bootstrap + happy-path examples documented |
| REFACTOR-07 | npm run build zero-warn after Vue extraction | CSS scope migration rules documented |
| REFACTOR-08 | No circular imports introduced | Import graph and safe-order documented |
</phase_requirements>

---

## Summary

Phase 16 is a pure-refactor: move code between files without changing behaviour. The three monoliths were inspected directly. The safest order is purchases.py → tasks.py → MyTasksView.vue, each split from the most isolated helper outward to the core CRUD.

The dominant risk is not logic errors but import order: FastAPI resolves overlapping routes by registration order, and Python circular imports are possible if two new modules import each other. Both risks are eliminated by a defined safe extraction sequence and the rule "new module only imports from purchases.py/tasks.py originating file, never the reverse until all extractions are done."

**Primary recommendation:** Follow the extraction sequence in Section 1 exactly. Run `npx playwright test --grep "@smoke"` (subset tag) after each commit for fast feedback; run the full suite before push.

---

## Standard Stack

### Core (no new dependencies needed)
| Library | Purpose | Note |
|---------|---------|------|
| FastAPI APIRouter | Router decomposition | Already in project |
| SQLAlchemy async 2.0 | DB access in extracted routers | No change — same `Depends(get_db)` |
| Vue 3 `<script setup>` | Component extraction | Same pattern as Phase 15 / PurchaseItemsEditor |
| Vuetify 3 | UI components in extracted Vue | Same import style |
| pytest (bootstrap needed) | Smoke integration tests (D-27) | No backend/tests/ directory exists yet |

**Installation required:**
```bash
# Backend test bootstrap (one-time)
pip install pytest pytest-asyncio httpx
# Create backend/tests/__init__.py + conftest.py
```

---

## Architecture Patterns

### Section 1: Extraction Order and Dependency Graph

#### 1.1 purchases.py (3233 lines) — safe extraction order

**Dependency graph (confirmed by code inspection):**

```
purchase_export.py
  uses: ALL_EXPORT_COLUMNS, DEFAULT_EXPORT_COLUMNS, _get_cell_value, _PURCHASE_METHOD_LABELS,
        _PURCHASE_BASIS_LABELS, _CONTRACT_TYPE_LABELS, _STATUS_LABELS
  needs from purchases.py: Purchase model, Subsidy, Contractor (models), Workbook (openpyxl)
  cross-deps: NONE (no calls to _check_budget or _create_assignment_chat_room)

purchase_budget.py
  uses: _check_budget, FRAMEWORK_TYPES, _assign_framework_seq
  needs from purchases.py: Purchase, Subsidy (models), func, select
  cross-deps: NONE

purchase_items_import.py  (lines ~1847-2582 + top-level helpers _ocr_pdf_to_rows, _legacy_*)
  uses: _ocr_pdf_to_rows, _legacy_extract_tables, _legacy_detect_best_table,
        _upsert_product_to_catalog, GET/POST /items/import/*, GET /items/import/template
  needs from purchases.py: Purchase, PurchaseItem, Product (models), load_workbook, Workbook
  cross-deps: NONE to budget/members/transitions

purchase_transitions.py  (lines ~1016-1210)
  uses: transition_status, convert_service_note_to_order, STATUS_ORDER, TRANSITION_REQUIRED,
        FRAMEWORK_TYPES, _assign_framework_seq
  needs from purchases.py: _purchase_to_full (D-20 — stays in purchases.py), _item_to_out
  needs from purchase_budget.py: _check_budget (import from new module)
  cross-deps: calls ensure_contract_linked from contracts.py (already external)

purchase_members.py  (lines ~1245-1510)
  uses: assign_purchase, respond_purchase_consent, kanban_status_change, update_substatus,
        update_task_comment, users_list, _create_assignment_chat_room
  needs from purchases.py: Purchase, User, UserHierarchy (models)
  cross-deps: NONE to transitions/budget
```

**Safe extraction order (D-02 principle):**
1. `purchase_export.py` — zero cross-deps, pure Excel/column logic (~400 lines)
2. `purchase_items_import.py` — zero cross-deps, OCR/Excel import helpers at top of file (~750 lines including top-level _ocr_pdf_to_rows, _legacy_* that live before `router = APIRouter(...)`)
3. `purchase_budget.py` — zero cross-deps, only _check_budget + _assign_framework_seq (~150 lines)
4. `purchase_members.py` — no deps on above, uses _create_assignment_chat_room (~350 lines)
5. `purchase_transitions.py` — imports `_check_budget` from purchase_budget, imports `_assign_framework_seq` from purchase_budget (~200 lines)
6. `purchases.py` (residual) — CRUD + _purchase_to_full + _item_to_out + list + get + create + update + delete + bulk_delete + my-tasks + kanban-all + kp-items + by-contract + list_purchase_tasks (~600 lines)

**Critical discovery:** `_ocr_pdf_to_rows` and `_legacy_*` functions appear at lines 44-141 of purchases.py, BEFORE `router = APIRouter(...)`. They belong to `purchase_items_import.py` but are physically at the top. Extractor must move them to the new file — do NOT leave them in purchases.py.

**Cross-file import at L1392-1406:** `list_purchase_tasks` in purchases.py does `from app.routers.tasks import _enrich_tasks`. After tasks.py is split, this import must be updated to `from app.routers.task_visibility import _enrich_tasks` (if that's where it ends up). Research Section 1.2 below confirms `_enrich_tasks` goes to task_visibility.py.

#### 1.2 tasks.py (1698 lines) — safe extraction order

**Dependency graph (confirmed by code inspection):**

```
task_visibility.py
  uses: _get_visible_user_ids (L25-75), _enrich_tasks (L111-277)
  these two are called by: list_tasks (CRUD), org_summary, badges, list_purchase_tasks in purchases.py
  cross-deps: NONE — only models, no other router imports

task_comments.py
  uses: GET/POST/DELETE /{id}/comments, dismiss-field, broadcast endpoints
  needs: TaskComment, TaskChange, TaskFieldSeen (models)
  cross-deps: NONE to visibility/badges/delegation

task_badges.py
  uses: GET /badges, GET /org-summary, GET /init (L370-862)
  needs: _get_visible_user_ids (import from task_visibility)
  cross-deps: only task_visibility, no cycles

task_delegation.py
  uses: GET /pending-consent, POST /{id}/consent, GET /consent-declines,
        POST /consent-declines/{id}/acknowledge, _create_task_chat_room, _set_assignees
  needs: _get_visible_user_ids (import from task_visibility), _enrich_tasks (import from task_visibility)
  cross-deps: task_visibility only

tasks.py (residual CRUD)
  uses: list_tasks (L291-367), get_task, subtasks, create_task, update_task, patch_task,
        review_complete, categories, departments
  needs: _get_visible_user_ids, _enrich_tasks (import from task_visibility)
  needs: _set_assignees (import from task_delegation)
  cross-deps: task_visibility, task_delegation (import only, no back-edge)
```

**Safe extraction order:**
1. `task_visibility.py` — `_get_visible_user_ids` + `_enrich_tasks` (both used everywhere, must come first so others can import)
2. `task_comments.py` — zero deps on other split modules
3. `task_badges.py` — imports `_get_visible_user_ids` from task_visibility
4. `task_delegation.py` — imports `_get_visible_user_ids` + `_enrich_tasks` + `_set_assignees` (stays here, called by tasks.py CRUD via import)
5. `tasks.py` (residual CRUD) — imports from task_visibility + task_delegation

**After tasks.py split:** update import in `purchases.py` L1401:
```python
# Before:
from app.routers.tasks import _enrich_tasks
# After:
from app.routers.task_visibility import _enrich_tasks
```

#### 1.3 MyTasksView.vue (2188 lines) — state ownership

**Refs that are VIEW-LEVEL (stay in orchestrator):**
- `selectedOrgId`, `orgSummary`, `orgCardsOpen`, `orgLoading` — used in OrgSelector
- `activeTab`, `viewMode`, `taskViewMode` — tab/mode routing
- `tasks`, `archiveTasks`, `generalTasks` — primary data
- `pendingConsentTasks`, `pendingApprovals`, `consentDeclines` — cross-tab notifications
- `loading` — global load state

**Refs that are COMPONENT-LEVEL (migrate to child):**
- `taskForm`, `showTaskDialog`, `editingTask`, `taskComments`, `newCommentText` — TaskDetail dialog (stays in MyTasksView or extracts as TaskDetailDialog component if desired)
- `delegateForm`, `showDelegateDialog` — delegation dialog
- Purchases kanban/list rendering state — PurchasesTable.vue

**Shared state pattern (D-14 confirms):** Parent MyTasksView makes all `apiFetch` calls and passes data as props. Children emit events back (`update:modelValue` or named emits). No composable needed — props/emits sufficient given D-14 locks parent as "orchestrator with api calls."

**Decision: TasksTable + TasksKanban — two separate components (recommended)**
- D-16 explicitly names `TasksTable.vue` + `TasksKanban.vue` as separate files
- Code inspection: list mode (v-data-table) and kanban mode (v-for columns) share zero DOM structure
- Prop `:mode` approach would make one 800-line component with heavy v-if nesting
- **Conclusion:** Two components, parent passes `tasks` prop and `selected-org-id` to both, toggles visibility with `v-if="taskViewMode === 'list'"` / `v-if="taskViewMode === 'kanban'"`

Same pattern for PurchasesTable.vue + PurchasesKanban.vue (D-17).

---

### Section 2: FastAPI Router Split Pattern

#### 2.1 Exact template for new extracted router

```python
# purchase_export.py — follow purchase_files.py pattern exactly
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.contractor import Contractor
from app.auth.jwt import get_current_user
from io import BytesIO
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None

router = APIRouter(prefix="/api/purchases", tags=["purchase-export"])

# ... constants and helpers moved here ...

@router.get("/export/columns")
async def get_export_columns(_=Depends(get_current_user)):
    ...
```

**Registration in backend/app/__init__.py:**
```python
# After existing purchase_approvals.router, add:
app.include_router(purchase_export.router)
app.include_router(purchase_budget.router)
app.include_router(purchase_members.router)
app.include_router(purchase_transitions.router)
app.include_router(purchase_items_import.router)
# New tasks routers:
app.include_router(task_visibility.router)  # if it has any endpoints (org-summary/badges moved here)
app.include_router(task_badges.router)
app.include_router(task_delegation.router)
app.include_router(task_comments.router)
```

Note: `task_visibility.py` may have no router (pure helper module). Only mount if it has endpoints.

#### 2.2 Overlapping prefix route resolution

**Rule (HIGH confidence — FastAPI/Starlette behavior):**
- FastAPI registers routes in the order `include_router` is called.
- Within a single prefix, more specific paths (e.g. `/export/columns`) match before path parameters (`/{pid}`).
- CRITICAL: `/export/columns` vs `/{pid}` — FastAPI checks concrete segments first, so `GET /api/purchases/export/columns` will NOT be captured by `GET /api/purchases/{pid}` because FastAPI tries static routes before parametric ones within the same router.
- RISK: If `purchases.router` contains `/{pid}` AND `purchase_export.router` contains `/export/columns`, and `purchases.router` is registered FIRST, FastAPI will correctly route `/export/columns` to the export router because static `export` segment beats `{pid}` parameter. **This is safe.**
- VERIFY with `test_routers_mounted.py` — GET /api/purchases/export/columns must return 200, not 404 or wrong handler.

**Registration order rule:** Register ALL specific-path routers (export, budget, members, transitions, items_import) AFTER the primary `purchases.router`. FastAPI merges all routes from all registered routers and then sorts them — static segments outrank path parameters.

#### 2.3 Private helper export convention

**Convention (D-19 + discretion):** Keep underscore prefix on private helpers that are importable cross-module. Python underscore convention means "internal" not "private" — it is legal to import `_foo` from another module. Keeping underscore visually signals "this is not a public API helper."

```python
# purchase_budget.py
async def _check_budget(...):  # keep underscore
    ...

# purchase_transitions.py
from app.routers.purchase_budget import _check_budget  # valid import
```

#### 2.4 Circular import risk

**Assessment: NO circular import risk given the extraction order.**

Dependency direction is strictly one-way:
```
task_visibility ← task_badges, task_delegation, task_comments, tasks (CRUD)
purchase_budget ← purchase_transitions, purchases (CRUD)
purchase_members ← purchases (CRUD) [only if purchases.py calls something from members — it doesn't]
```

The existing cross-file import `from app.routers.tasks import _enrich_tasks` (in purchases.py L1401) creates a `purchases → tasks` edge. After split: `purchases → task_visibility`. No cycle.

**One confirmed back-edge to watch:** `task_badges.py` calls `_get_visible_user_ids` from `task_visibility.py`, AND `task_visibility.py` has no imports from `task_badges.py`. Safe.

---

### Section 3: Vue Component Extraction Pattern

#### 3.1 Phase 15 (PurchaseItemsEditor) pattern — apply identically

```typescript
// OrgSelector.vue — props + emits pattern
<script setup lang="ts">
const props = defineProps<{
  orgSummary: Array<{org_id: number | null, org_name: string, task_count: number, purchase_count: number, unseen_count: number}>
  selectedOrgId: number | null
  orgCardsOpen: boolean
}>()

const emit = defineEmits<{
  'select-org': [orgId: number | null]
  'update:orgCardsOpen': [value: boolean]
}>()
</script>
```

Parent passes data as props. Child emits actions. No Pinia — state lives in MyTasksView refs.

#### 3.2 CSS scope migration rule

When extracting a component, search MyTasksView.vue `<style scoped>` for selectors that match elements moved to the child. Move those CSS blocks to child's `<style scoped>`. If selector is used in both parent and child, copy to child and keep in parent (duplication is acceptable for scoped styles).

Key selectors to check: `.org-cards-grid`, `.org-sel-card`, `.org-sel-card--all`, `.osc-*` → belong to OrgSelector.vue.

#### 3.3 apiFetch call location (confirmed by D-14)

All `apiFetch` calls stay in `MyTasksView.vue`. Children receive loaded data as props and call `emit('refresh')` to trigger parent reload. No API calls in child components.

Exception: task comments poll timer (`_commentsPollTimer` in loadComments) — this is complex enough state that it can remain in MyTasksView's dialog section or be extracted into a `TaskDetailDialog.vue` sub-component (Claude's discretion — not in D-14..D-18 scope explicitly).

---

### Section 4: Testing Strategy

#### 4.1 E2E test files and coverage

14 spec files found in `e2e/`:
```
01-auth.spec.ts          — auth endpoints
02-all-pages.spec.ts     — page load smoke (hits /my-tasks)
03-dashboard.spec.ts     — dashboard
04-subsidies.spec.ts     — subsidies
05-orders.spec.ts        — /api/purchases/* (CRUD, transitions, files, members)
06-contracts.spec.ts     — contracts
07-contractors.spec.ts   — contractors
08-products.spec.ts      — products
09-staff-hierarchy.spec.ts — hierarchy
10-other-pages.spec.ts   — misc pages
11-navigation.spec.ts    — nav
12-publications.spec.ts  — publications
13-chat-ui.spec.ts       — chat
18-purchase-items-editor.spec.ts — Phase 15 items editor
```

**Files hitting purchases routes:** `05-orders.spec.ts` (primary), `02-all-pages.spec.ts` (smoke load).
**Files hitting tasks routes:** `02-all-pages.spec.ts` (loads /my-tasks), likely `05-orders.spec.ts` for linked tasks.
**Files hitting /my-tasks view:** `02-all-pages.spec.ts`.

**Minimum fast subset between commits:** `05-orders.spec.ts` + `02-all-pages.spec.ts` + `18-purchase-items-editor.spec.ts` (covers most purchase and tasks endpoints).

```bash
# Fast gate (~3 specs, ~30-60s):
npx playwright test e2e/05-orders.spec.ts e2e/02-all-pages.spec.ts e2e/18-purchase-items-editor.spec.ts

# Full gate (before push):
npx playwright test
```

#### 4.2 Smoke integration test bootstrap

No `backend/tests/` directory exists. Wave 0 must create it.

```
backend/tests/
├── __init__.py
├── conftest.py          # AsyncClient + app fixture
└── test_routers_mounted.py
```

**conftest.py pattern (FastAPI + httpx async):**
```python
import pytest
from httpx import AsyncClient, ASGITransport
from app import create_app  # or wherever app is created

@pytest.fixture
async def client():
    from app import app  # the FastAPI instance
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

**test_routers_mounted.py pattern:**
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
@pytest.mark.parametrize("path,method,expected_not", [
    ("/api/purchases/export/columns", "GET", [404]),
    ("/api/purchases/export/excel", "GET", [404]),
    ("/api/purchases/my-tasks", "GET", [404]),
    ("/api/tasks/badges", "GET", [404]),
    ("/api/tasks/org-summary", "GET", [404]),
    ("/api/tasks/consent-declines", "GET", [404]),
])
async def test_router_mounted(client: AsyncClient, path, method, expected_not):
    resp = await client.request(method, path)
    # 401/403 = auth required = router IS mounted
    # 404 = router NOT mounted (failure)
    assert resp.status_code not in expected_not, f"{method} {path} returned {resp.status_code}"
```

**Run command:** `pytest backend/tests/test_routers_mounted.py -v`

#### 4.3 Frontend visual regression

No automated screenshot baseline exists. Manual UAT checklist:
- [ ] /my-tasks loads with org cards visible
- [ ] Switching between Задачи / Закупки tabs works
- [ ] Kanban and List view toggles work for both tabs
- [ ] OrgSelector card click filters tasks and purchases
- [ ] Consent cards render and respond
- [ ] Report tab renders (no blank screen)

---

### Section 5: `__init__.py` Registration Order

Current L281-318 order (38 routers). Purchase cluster: `purchases.router` (L285) → `purchase_files.router` (L293) → `purchase_events.router` (L301) → `purchase_approvals.router` (L307).

**New routers insertion point — after purchase_approvals (L307):**
```python
app.include_router(purchases.router)          # existing — must stay in place
# ... other existing routers ...
app.include_router(purchase_files.router)     # existing
app.include_router(purchase_events.router)    # existing
app.include_router(purchase_approvals.router) # existing
# NEW — insert here:
app.include_router(purchase_export.router)
app.include_router(purchase_items_import.router)
app.include_router(purchase_budget.router)    # no endpoints, may skip if no @router.X
app.include_router(purchase_members.router)
app.include_router(purchase_transitions.router)
```

Tasks cluster — after `tasks.router` (L308):
```python
app.include_router(tasks.router)              # existing
# NEW — insert after tasks:
app.include_router(task_visibility.router)    # only if it has endpoints
app.include_router(task_badges.router)
app.include_router(task_delegation.router)
app.include_router(task_comments.router)
```

**Route ordering safety:** All new routers share prefix with parent (`/api/purchases`, `/api/tasks`). FastAPI resolves static segments before parametric — `GET /api/purchases/export/columns` will not collide with `GET /api/purchases/{pid}`. Verified by reading FastAPI routing source behavior (confidence: MEDIUM — based on known Starlette behavior; validated by test_routers_mounted.py).

---

### Section 6: Phase-Specific Gotchas

**G-01: `from sqlalchemy import case` (not `func.case()`)** — purchases.py must preserve this import. When creating purchase_export.py or purchase_members.py, check if `case` is used. If yes, import it correctly.

**G-02: `_ocr_pdf_to_rows` and `_legacy_*` functions** are defined at TOP of purchases.py (L44-141), BEFORE `router = APIRouter(...)`. They logically belong to `purchase_items_import.py`. Executor must move them as a unit and update the `router = APIRouter(...)` declaration at L144 (which stays in purchases.py).

**G-03: Authorization guards — reproduce exactly.** Every endpoint in the new modules must carry the SAME `Depends(require_role(*ROLES))` as the original. Do not drop or loosen guards during extraction. Grep before and after: `grep -n "require_role\|get_current_user" backend/app/routers/purchase_*.py`.

**G-04: `purchase_files.py` already handles `/{pid}/files` endpoint.** purchases.py does NOT duplicate this — confirmed by code inspection. No conflict risk.

**G-05: `_create_assignment_chat_room` in purchases.py (L147-182) is independent of chat.py.** It creates ChatRoom/ChatParticipant/ChatMessage directly via DB — it does NOT call chat_manager WebSocket methods. Safe to move to purchase_members.py without touching chat.py.

**G-06: `list_purchase_tasks` in purchases.py (L1392-1406) imports `_enrich_tasks` from tasks.** After tasks.py is split, this import must become `from app.routers.task_visibility import _enrich_tasks`. This update must be in the same commit as the task_visibility extraction.

**G-07: `ALL_EXPORT_COLUMNS`, `DEFAULT_EXPORT_COLUMNS`, `_get_cell_value`, and the 4 `_*_LABELS` dicts** are currently defined between L193-321 — they belong exclusively to purchase_export.py and can be moved cleanly.

**G-08: `TRANSITION_REQUIRED` dict (L372-377)** belongs to purchase_transitions.py. `STATUS_ORDER` (L186) is used by BOTH purchases.py (CRUD create/update/my-tasks) AND purchase_transitions.py (transition_status) AND purchase_members.py (kanban_status_change). Resolution: keep `STATUS_ORDER` in purchases.py (core CRUD), export it: `from app.routers.purchases import STATUS_ORDER`.

**G-09: `_purchase_to_full` + `_item_to_out` (D-20)** stay in purchases.py. purchase_transitions.py calls `_purchase_to_full` to build the return value after transition. After extraction: `from app.routers.purchases import _purchase_to_full`. This creates a `purchase_transitions → purchases` import edge — safe, no cycle.

**G-10: Vue `<style scoped>` — imap-* CSS precedent from Phase 15.** Phase 15 moved `imap-*` CSS into PurchaseItemsEditor scoped style. Apply same discipline: if CSS selector only affects DOM inside an extracted component, move it. Use browser devtools if uncertain.

**G-11: Autodeploy triggers on every push.** Each atomic commit that is pushed triggers Docker rebuild. The commit MUST be build-green. Never push a "work in progress" commit mid-extraction.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Route conflict detection | Manual URL audit | test_routers_mounted.py + playwright 05-orders | FastAPI raises at startup if truly conflicting |
| Private helper discoverability | Re-document in README | Keep underscore + import directly | Python convention — underscore = "internal but importable" |
| State management across extracted Vue components | Pinia store | Props + emits (D-14 locked) | Orchestrator pattern keeps API calls centralized |
| Type sharing across Vue files | Copy types | TypeScript `import type` from parent or shared types file | Single source of truth |

---

## Validation Architecture

> nyquist_validation: enabled (absent from config = treat as enabled)

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (needs bootstrap — see Wave 0 gaps) |
| E2E Framework | Playwright |
| Config file | pytest.ini or pyproject.toml [tool.pytest] (create in Wave 0) |
| Quick run command | `pytest backend/tests/test_routers_mounted.py -v` |
| Full E2E command | `npx playwright test` |

### Invariants per Extracted Module

| Module | Invariant | Test Command |
|--------|-----------|--------------|
| purchase_export.py | GET /api/purchases/export/columns returns 200 (with auth) | pytest test_routers_mounted.py::test_router_mounted[export-columns] |
| purchase_budget.py | _check_budget raises 422 when over limit; no endpoint mount needed | unit test or integration: POST /api/purchases/ with over-budget amount |
| purchase_members.py | PATCH /api/purchases/1/assign returns 200 or 401 (not 404) | pytest test_routers_mounted.py |
| purchase_transitions.py | POST /api/purchases/1/transition?status=plan_schedule returns 200 or 422 or 401 (not 404) | pytest test_routers_mounted.py |
| purchase_items_import.py | GET /api/purchases/items/import/template returns 200 (with auth) | pytest test_routers_mounted.py |
| task_visibility.py | _get_visible_user_ids returns None for superadmin, set otherwise | integration via task list: GET /api/tasks/ returns correct filtered list |
| task_badges.py | GET /api/tasks/badges returns 200 or 401 (not 404) | pytest test_routers_mounted.py |
| task_delegation.py | GET /api/tasks/pending-consent returns 200 or 401 (not 404) | pytest test_routers_mounted.py |
| task_comments.py | GET /api/tasks/1/comments returns 200 or 401 or 404 (not "router missing") | pytest test_routers_mounted.py |
| OrgSelector.vue | Org cards render, click sets selectedOrgId | Manual UAT + 02-all-pages.spec.ts |
| TasksTable.vue + TasksKanban.vue | Tasks list/kanban visible after tab switch | 02-all-pages.spec.ts |
| PurchasesTable.vue + PurchasesKanban.vue | Purchases kanban/list visible | 05-orders.spec.ts |

**"0 regression" definition:** All 70 E2E tests pass on prod deploy after each wave of extractions. `npm run build` exits 0 with no TypeScript errors. All 10 new routers respond with non-404 (auth-protected = 401/403 acceptable) to their primary GET endpoints.

### Wave 0 Gaps
- [ ] `backend/tests/__init__.py` — empty init file
- [ ] `backend/tests/conftest.py` — AsyncClient + app fixture
- [ ] `backend/tests/test_routers_mounted.py` — parametrized mount checks
- [ ] `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` — asyncio_mode = auto
- [ ] `pip install pytest pytest-asyncio httpx` — framework install

---

## Common Pitfalls

### Pitfall 1: Forgetting to update cross-file imports in same commit
**What goes wrong:** purchases.py imports `_enrich_tasks` from tasks.py. After splitting task_visibility.py, the import in purchases.py still points to tasks.py, which no longer has it. Docker build fails.
**How to avoid:** Before each extraction, grep ALL files that import from the source module: `grep -r "from app.routers.tasks import" backend/`. Update ALL callers in the same commit.

### Pitfall 2: Moving `STATUS_ORDER` without updating both callers
**What goes wrong:** `STATUS_ORDER` is used in purchases.py CRUD (my-tasks endpoint filters by status), purchase_transitions.py, AND purchase_members.py (kanban_status_change). Moving to purchase_transitions.py breaks the other two.
**How to avoid:** Keep `STATUS_ORDER` in purchases.py (the residual CRUD module). Export it: `from app.routers.purchases import STATUS_ORDER`.

### Pitfall 3: Leaving `_ocr_pdf_to_rows` in purchases.py
**What goes wrong:** These functions are at L44-141, BEFORE `router = APIRouter(...)`. An extractor who starts at `router = APIRouter(...)` will miss them and leave them in purchases.py, creating a situation where purchase_items_import.py imports them from purchases.py (valid but defeats the purpose).
**How to avoid:** purchase_items_import.py extraction must start from L44 (the `_ocr_pdf_to_rows` function) not from the first `@router.X` decorator.

### Pitfall 4: Vue prop drilling leading to wide prop signatures
**What goes wrong:** OrgSelector.vue needs `orgSummary`, `selectedOrgId`, `orgCardsOpen` — all from parent. If not explicitly typed, TypeScript errors or runtime errors occur.
**How to avoid:** Use `defineProps<{...}>()` with exact types. Check the MyTasksView.vue `orgSummary` ref type for the exact interface shape.

### Pitfall 5: FastAPI startup route conflict error
**What goes wrong:** If two routers register the EXACT same path+method combination (not overlapping parametric), FastAPI raises ValueError at startup. Docker container exits immediately.
**How to avoid:** `TRANSITION_REQUIRED`, `STATUS_ORDER` and other constants must not create duplicate `@router.X` decorators. Run `docker compose logs backend --tail 30` after each rebuild.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Single monolith router | Thematic router modules (already proven in purchase_files.py, purchase_events.py) | Existing pattern — just apply consistently |
| Vue view as monolith | Co-located component extraction (Phase 14 Radar, Phase 15 PurchaseItemsEditor) | Proven in this codebase |

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection: `backend/app/routers/purchases.py` (3233 lines) — all function locations confirmed
- Direct code inspection: `backend/app/routers/tasks.py` (1698 lines) — all function locations confirmed
- Direct code inspection: `frontend/src/views/MyTasksView.vue` (2188 lines) — state ownership confirmed
- Direct code inspection: `backend/app/__init__.py` L281-318 — router registration order confirmed
- Direct code inspection: `backend/app/routers/purchase_files.py` — canonical split pattern confirmed
- `CONTEXT.md` — all decisions D-01..D-28 read and applied

### Secondary (MEDIUM confidence)
- FastAPI route ordering behavior — based on Starlette routing knowledge; validated by test pattern
- pytest-asyncio + httpx ASGITransport pattern — standard FastAPI testing pattern

### Tertiary (LOW confidence)
- E2E test run time estimates — not measured, based on typical Playwright timing

---

## Metadata

**Confidence breakdown:**
- Extraction order: HIGH — based on direct dependency inspection of every function
- Import graph (circular risk): HIGH — confirmed by reading all import statements
- Router registration order: MEDIUM — FastAPI behavior confirmed by pattern, test validates
- Vue state ownership: HIGH — every ref inspected in script setup

**Research date:** 2026-04-19
**Valid until:** 2026-06-01 (stable stack, no fast-moving dependencies)
