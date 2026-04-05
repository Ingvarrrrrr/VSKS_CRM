---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_plan: 1
status: executing
stopped_at: Completed 07-05-PLAN.md
last_updated: "2026-04-05T20:36:15.275Z"
progress:
  total_phases: 11
  completed_phases: 3
  total_plans: 21
  completed_plans: 18
---

# STATE.md — VSKS_CRM

## Current State

- **Phase:** 06-analytics-budget-history
- **Current Plan:** 1
- **Status:** Executing Phase 07
- **Last Updated:** 2026-04-04
- **Stopped At:** Completed 07-05-PLAN.md

---

## Completed Phases

### Phase 1: Purchase Form + Status Workflow ✅

Completed before GSD tracking started.

- Purchase model extended to 40+ columns (18+ new fields added)
- 5-step status workflow: `planned → confirmed → contracted → delivered → paid`
- Role-gated transitions: Manager cannot go backward; Admin-only reverse
- `economy` auto-calculates client-side
- All 390 ФАДМ_2026 purchases migrated intact; `feo_category_id` = NULL for legacy rows
- Status chips with distinct colors; status filter in list view

---

### Phase 2: Cascading FEO + Budget Validation ✅

Completed before GSD tracking started.

- 3-level cascading FEO selectors (selecting L1 clears L2+L3, etc.)
- `_check_budget()` helper with real-time budget enforcement
- Admin override with confirmation dialog for over-limit saves
- FeoCategoriesView — add/edit FEO categories in modal without page reload
- Budget indicator shows "Остаток" / "Превышение" in real time

---

### Phase 3: File Attachments ✅

Completed before GSD tracking started; enhanced in later commits.

- `purchase_items` table created
- `purchase_files` upload / download / delete endpoints
- Excel export with file metadata columns
- **Later enhancements (post-GSD, tracked below):**
  - SHA-256 deduplication (commit 585a3cd)
  - Typed upload slots: Договор / Акт / УПД / Платёжка (commit 209941c)
  - 409 rejection on duplicate file upload (commit 0d98a90); older file of same type auto-deactivated

---

### Phase 4: Contract Registry ✅

Completed before GSD tracking started; heavily enhanced afterward.

- `docxtpl`-based document template engine; `routers/documents.py`
- Contract model with three contract types; spending ceiling for framework-limited contracts
- `current_amount` = live sum of linked purchases' `planned_total_price`
- **Later enhancements (post-GSD, tracked below):**
  - ContractsView full redesign: row-click navigation, product search, filtered dropdowns
  - Export as ZIP archive
  - Contract import from PDF / Excel / Word with drag-and-drop + FileDropZone component

---

### Phase 5: Export / Import Excel ✅

Completed before GSD tracking started; enhanced afterward.

- SubsidiesView FEO tree
- ContractorsView Excel import
- `GET /api/purchases/export` → valid `.xlsx` in GoodsService column format
- All 390 ФАДМ_2026 purchases appear in export for `subsidy_id=7`
- **Later enhancements (post-GSD, tracked below):**
  - Contract import from PDF / Excel / Word with drag-and-drop (commit 43eb646)

---

### Phase 6: Analytics + Budget History ✅

Fully implemented.

**Done:**

- Dashboard KPIs + charts loaded and functional
- BudgetDrillDownDialog exists and displays FEO drill-down data (all 3 levels confirmed)
- budget_history table created (plan 06-01); hooks write rows on purchase price and subsidy limit changes
- `GET /api/subsidies/{id}/history` paginated endpoint implemented (plan 06-02)
- BudgetHistoryDialog.vue timeline component created; wired into SubsidiesView.vue (plan 06-03)

---

### Phase 7: Roles + Wishes Workflow — PARTIAL ⚠️

Role enforcement and delegation done; Wishes lifecycle not implemented.

**Done:**

- Hierarchy editor (HierarchyView)
- Departments management (DepartmentsView)
- Task delegation — task assignment by role
- Multi-org membership (UserOrganization model, org switching)
- `org_admin` role fix (commit a5bf274)
- BFF endpoint for tasks (`/api/tasks/my`)
- Review status on tasks

**Done (07-01):**

- Wish SQLAlchemy model (D-02 columns), schemas (WishCreate/Update/Reject/Convert/Out), migration applied
- GET /api/wishes endpoint with org isolation + employee filter — router registered
- service_note_text/by/at columns added to purchases table

**Done (07-02):**

- POST /api/wishes (create, draft, org isolation)
- PUT /api/wishes/{id} (update draft, creator only)
- POST /api/wishes/{id}/submit (draft -> submitted, creator only)
- POST /api/wishes/{id}/approve (submitted -> approved, MANAGER_ROLES)
- POST /api/wishes/{id}/reject (submitted -> rejected + reason, MANAGER_ROLES, D-08)
- POST /api/wishes/{id}/convert (approved -> converted + inline Purchase, ADMIN_ROLES, D-23)
- DELETE /api/wishes/{id} (draft only, creator only, 204)
- Employee purchase list strictly filtered to assigned_user_id = current_user.id (D-13)

**Not done:**

- "Мои заявки" view for Viewers
- "Заявки сотрудников" view for Managers

---

### Phase 8: Торговые площадки + КП email + E2E ✅

Fully tracked in GSD. Completed 2026-03-20.

- `roseltorg_publish.json` (n8n, production URL + token check + `procedure_type` mapping) — активен на сервере
- `fabrikant_publish.json` (test mode `FABRIKANT_TEST_MODE=true`) — активен на сервере; IP whitelist добавлен 2026-03-30
- `CreateOrderView.vue` — двухшаговый диалог с dropdown для Росэлторг
- E2E тесты (`e2e/12-publications.spec.ts`) — 4 теста, все pass
- n8n env: `ROSELTORG_TOKEN`, `FABRIKANT_TEST_MODE=true`
- n8n admin password: `Admin123!` (был reset)
- SMTP настроен: `z@vsks.ru` → `zakupki@vsks.ru`
- **Key decisions recorded in GSD plans 08-01 – 08-04**

---

## Post-Phase 8 Work (untracked, delivered after Phase 8)

All items below were merged to `main` / `claude` branch outside any GSD phase plan.

| Feature | Commit(s) | Notes |
|---------|-----------|-------|
| n8n removed; direct API calls for Фабрикант и Росэлторг.Бизнес | 265c68e | Simplified architecture — no n8n middleware |
| SMTP configured (z@vsks.ru) | — | Yandex 360 app password set in docker-compose.yml |
| PWA + mobile navigation | 1f5b9e2 | Service worker, manifest, mobile-optimised navbar |
| Telegram integration — reply button + inline consent flow | 5c9008e, 202f2e8 | Bot token + webhook; consent stored per user |
| org_admin role fix | a5bf274 | org_admin could not see own org data; fixed filter logic |
| SHA-256 file deduplication | 585a3cd | Duplicate file upload silently returns existing record |
| Typed upload slots (Договор / Акт / УПД / Платёжка) + active/inactive toggle | 209941c | Each slot holds one active file; older files deactivated |
| Duplicate file upload → 409 + auto-deactivate older file of same type | 0d98a90 | Client shows conflict message instead of silent failure |
| Contract import from PDF / Excel / Word with drag-and-drop | 43eb646 | Parsed server-side; preview before confirmation |
| Universal FileDropZone component | be7e629 | Reusable drop zone used by contract import and purchase files |
| Purchase member consent + notifications | — | Members added to purchases; consent tracked; notifications sent |
| Review status on tasks | — | Tasks can be marked "under review" before completion |
| Tasks BFF endpoint (`/api/tasks/my`) | — | Aggregated view for MyTasksView |
| Dark mode fixes | — | Multiple components adjusted for dark theme consistency |
| Draggable columns in table views | — | Column order persisted to localStorage |

---

## Active Phase

**None currently active.** Next logical work:

1. Complete Phase 6 (budget history write-on-change + history API + UI timeline)
2. Complete Phase 7 (Wishes lifecycle)
3. Multi-tenancy org-isolation audit (see Additional Work below)

---

## Additional Work Identified (not in original roadmap)

- **Multi-tenancy org-isolation audit** — `org_id` filter missing or unverified in: `contracts.py`, `feo_categories.py`, `dashboard.py`, `payments.py`, `commercial_requests.py`, `publications.py`, `subsidy_approvers.py`, `responsible_persons.py`
- **Dead code cleanup** — `AddProductDialog×3`, `ProductSelector×3`, `DashboardViewSimple`, `CreateOrderViewSimple`, `CreateOrderView.backup`
- **Landing page + dark theme** — ✅ completed (`LandingView.vue`, `vuetify.ts` dark theme, router guards)
- **Multi-tenancy frontend** — ✅ completed (`RegisterView`, `VerifyEmailView`, `OrganizationsView`, `AppBar` updates)

---

## Accumulated Context

### Roadmap Evolution

- Phase 8 added: Торговые площадки + КП email + E2E (n8n Росэлторг, Фабрикант test mode, SMTP КП, Playwright)
- Post-Phase-8 work above supersedes some Phase 8 decisions (n8n removed in favour of direct API calls)
- Phase 10 added: Chat Telegram-style UI — real-time delivery fix, sticky header, dual-mode search, Telegram-like polish
- Phase 11 added: Fix task display per-user org filtering — badges show wrong org, org selector shows orgs with no tasks, task scoping broken

---

## Blockers

- ~~SMTP~~ ✅ настроен
- ~~Фабрикант~~ ✅ IP whitelist добавлен 2026-03-30, публикация работает

---

## Key Decisions

- [06-01] Old budget_history table (mismatched schema: old_budget/new_budget/user_id columns, 1 orphaned test row) dropped and recreated — plan explicitly allowed this
- [06-01] Inline import `from app.models.budget_history import BudgetHistory as _BH` inside route functions avoids circular import risk
- [06-01] create_purchase hook uses existing db.flush() at line 628 so p.id is populated before writing history row
- [06-02] old_value/new_value typed as Optional[float] in BudgetHistoryItemOut (not Decimal) for clean JSON serialisation
- [06-02] `/{subsidy_id}/history` route appended after all existing routes to avoid FastAPI path conflict with `/{subsidy_id}` integer route
- [06-03] open() expose pattern chosen over v-model for BudgetHistoryDialog — simpler imperative trigger from parent without extra boolean ref
- [06-03] History button placed between approvers (mdi-account-multiple) and edit (mdi-pencil) buttons in subsidy card action row
- [09-05] `watch(totalUnread)` in AppBar syncs WS-driven badge without coupling to composable internals — single source of truth
- [09-05] `initChat()` called from AppBar (always-mounted component) as the WS lifecycle owner; polling fallback every 60s
- [09-05] `_badgeInterval` now cleared in `onUnmounted` (was previously not cleaned up — memory leak fixed)
- [09-04] Module-level refs (`totalUnread`, `wsConnected`) allow global badge display in AppBar without prop drilling
- [09-04] `onChatEvent` registry pattern: ChatView registers/unregisters on mount/unmount — clean separation from WS lifecycle
- [09-04] Employee role allowed `/chat` — chat is universal communication, not admin-only
- [09-02] In-memory Dict[int, List[WebSocket]] keyed by user_id chosen over Redis — single Docker instance makes external state store unnecessary
- [09-02] `send_to_user` catches all exceptions silently — callers must not be interrupted by stale/offline connections
- [09-02] proxy_read_timeout/proxy_send_timeout set to 86400s — nginx default 60s would disconnect idle WebSocket connections
- [09-03] `ws_router` uses separate `APIRouter()` without prefix so WS path resolves to `/api/ws/chat` as frontend expects
- [09-03] `chat_unread` in `/api/tasks/badges` wrapped in `try/except` — graceful degradation before DB migration runs
- [09-03] `pg_insert` with `on_conflict_do_update` used for UPSERT on `message_reads` (constraint `uq_message_read`)
- [10-03] `v-html` with `highlightSearch()` used for message highlight — XSS safe because user input is regex-escaped before use in replace
- [10-03] `min_length=2` FastAPI Query guard on `/chat/search` prevents expensive single-char DB full-table scans
- [10-03] Dual-mode search: single `searchQuery` ref drives `filteredRooms` or `filteredMessages` based on `selectedRoom` presence
- [07-01] Old wishes table (subsidy_id/user_id/name schema, 0 rows) dropped and recreated with D-02 schema — no data loss
- [07-01] alembic/env.py updated to use DATABASE_URL env var for Docker db-host connectivity (was hardcoded to localhost)
- [07-01] WishOut creator_name/approver_name are computed in router (not DB columns) via lazy="joined" relationships
- [07-05] update_subsidy/delete_subsidy inline role checks replaced with require_role dependency — consistent pattern, no behavior change
- [07-05] 7 feo_categories endpoints that had zero authentication (create, update, delete, move, import, export, purchase-totals) now gated with require_role(*ADMIN_ROLES) — critical security fix
- [07-05] contracts import endpoints (preview, mapped) upgraded from get_current_user to require_role(*MANAGER_ROLES)
- [07-02] Employee purchase filter uses q.where(Purchase.assigned_user_id == current_user.id) with no NULL fallback — D-13 strict compliance
- [07-02] convert_wish creates Purchase inline via db.flush() pattern (not HTTP call to create_purchase) — avoids budget check side-effects on wish-origin purchases
- [07-02] selectinload() used explicitly in _load_wish() helper rather than relying on model-level lazy="joined" — explicit async session behavior
- Multi-tenancy: `org_id` on all entities; superadmin sees all; `org_admin` / manager / employee see own org only
- Files stored as PostgreSQL bytea (no S3/MinIO)
- Status workflow is unidirectional; admin-only reverse approved
- Tech stack locked: Vue 3 + FastAPI + PostgreSQL
- n8n removed post-Phase-8 — direct REST API calls to Фабрикант и Росэлторг instead
- [08-01] `procedure_type` оставлен `Optional[str]` без enum-валидации — значения `templateId` уточнятся после токена Росэлторг
- [08-01] Обогащение n8n payload в `publish_purchase` (не в `_build_publish_payload`) — сохраняет чистоту helper-функции
- [08-02] `ROSELTORG_TOKEN` env var in n8n — empty token causes error callback with descriptive message (не падает молча)
- [08-02] `FABRIKANT_TEST_MODE` проверяется как строка `=== 'true'` для совместимости с n8n Variables
- [08-03] Росэлторг publish uses two-step dialog with mandatory `procedure_type` dropdown; `procedure_type` sent to API in request body
- [08-04] 409 on duplicate publication handled gracefully — GET existing pub list as fallback; nginx 307 redirect drops auth header — use trailing slash URLs; create-order route is `/orders/{id}/edit`

---

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | Улучшить визуализацию FruitShop магазина | 2026-03-27 | 199a137 | [1-fruitshop](./quick/1-fruitshop/) |

---

## Notes

- Real data: 390 purchases (ФАДМ_2026, `subsidy_id=7`), 612 contractors
- All 390 ФАДМ_2026 purchases have `feo_category_id=NULL`; total 36.8M₽ vs limit 15.5M₽ — historical overage, must not be blocked retroactively
- `subsidy_id=7` (ФАДМ_2026) requires `?admin_override=true` for new purchases
- Docker: NO volume mount for code → any change requires image rebuild
