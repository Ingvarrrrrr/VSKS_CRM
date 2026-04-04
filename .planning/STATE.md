# STATE.md — VSKS_CRM

## Current State

- **Phase:** 09-vnutrenniy-chat
- **Current Plan:** 09-04 COMPLETE
- **Status:** Phase 09 Plan 04 executed — chat frontend (useChat.ts composable + ChatView.vue + /chat route)
- **Last Updated:** 2026-04-04
- **Stopped At:** Completed 09-04-PLAN.md

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

### Phase 6: Analytics + Budget History — PARTIAL ⚠️
Partially implemented; budget history log unverified.

**Done:**
- Dashboard KPIs + charts loaded and functional
- BudgetDrillDownDialog exists and displays FEO drill-down data

**Not verified / incomplete:**
- Every `planned_total_price` change should write to `budget_history` (not confirmed)
- Every subsidy `limit` change should write to `budget_history` (not confirmed)
- `GET /api/subsidies/{id}/history` paginated endpoint — existence unverified
- Budget history timeline / modal in subsidy detail view — not confirmed built

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

**Not done:**
- Wishes lifecycle (Viewer submits → Manager approves → Admin converts to purchase)
- `GET /api/wishes`, `POST /api/wishes`, transition endpoints
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

---

## Blockers

- ~~SMTP~~ ✅ настроен
- ~~Фабрикант~~ ✅ IP whitelist добавлен 2026-03-30, публикация работает

---

## Key Decisions

- [09-04] Module-level refs (`totalUnread`, `wsConnected`) allow global badge display in AppBar without prop drilling
- [09-04] `onChatEvent` registry pattern: ChatView registers/unregisters on mount/unmount — clean separation from WS lifecycle
- [09-04] Employee role allowed `/chat` — chat is universal communication, not admin-only
- [09-03] `ws_router` uses separate `APIRouter()` without prefix so WS path resolves to `/api/ws/chat` as frontend expects
- [09-03] `chat_unread` in `/api/tasks/badges` wrapped in `try/except` — graceful degradation before DB migration runs
- [09-03] `pg_insert` with `on_conflict_do_update` used for UPSERT on `message_reads` (constraint `uq_message_read`)
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
