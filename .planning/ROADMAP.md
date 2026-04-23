# ROADMAP.md — VSKS_CRM

## Overview

18 phases | 57+ requirements | Brownfield (existing codebase: auth, CRUD, dashboard, SubsidiesView, 390 purchases, 612 contractors)

**Status snapshot (2026-04-23):**
- ✅ Complete (13): 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 13, 15, 16
- 🟡 In progress (2): 10 (3/4 plans), 14 (3/4 plans)
- ⏳ Not started (3): 12 (4 plans ready), 17 (TBD), 18 (TBD)

---

## Phases

### Phase 1: Purchase Form + Status Workflow ✅ COMPLETED (pre-GSD)

**Goal:** Extend the purchase model with 18 new fields and implement the full 5-step status workflow with role-gated transitions.

**Requirements:** PURCHASE-01, PURCHASE-02, PURCHASE-03, PURCHASE-04, PURCHASE-05, PURCHASE-06, PURCHASE-07, PURCHASE-08, PURCHASE-09, PURCHASE-10, PURCHASE-11, PURCHASE-12, PURCHASE-13

**Dependencies:** None (builds on existing CRUD; existing ФАДМ_2026 data must remain intact)

**Success Criteria:**
1. All 390 existing purchases load without errors after the migration; `feo_category_id` remains NULL for legacy rows.
2. A new purchase can be created with all 18 new fields and saved; `economy` auto-calculates client-side.
3. `POST /api/purchases/{id}/transition?status=contracted` returns HTTP 422 when `contract_number` is missing, and HTTP 200 with updated purchase when it is present.
4. A Manager cannot transition a purchase backward (e.g., `paid → delivered`) — API returns HTTP 403.
5. The purchase list view shows status chips in distinct colors and the status filter returns only matching rows.

---

### Phase 2: Cascading FEO + Budget Validation ✅ COMPLETED (pre-GSD)

**Goal:** Implement 3-level cascading FEO selectors and real-time budget enforcement that blocks over-limit saves for non-admin users.

**Requirements:** FEO-01, FEO-02, FEO-03, FEO-04, FEO-05, FEO-06, FEO-07, BUDGET-01, BUDGET-02, BUDGET-03, BUDGET-04, BUDGET-05

**Dependencies:** Phase 1 (purchase form must exist; `feo_category_id` column must be present)

**Success Criteria:**
1. Selecting Level 1 clears Level 2 and Level 3; selecting Level 2 clears only Level 3 — verified in browser.
2. The FEO hierarchy API returns all three levels in one request (response time < 500 ms on dev).
3. "Add FEO category" button opens a modal that persists a new category at the chosen level; it appears immediately in the dropdown without page reload.
4. The budget indicator updates in real time as `planned_total_price` is typed; it shows "Остаток" or "Превышение" correctly against the subsidy limit.
5. A Manager attempting to save a purchase that exceeds the subsidy limit receives an error and the record is not created; an Admin can override with a confirmation dialog.

---

### Phase 3: File Attachments ✅ COMPLETED (pre-GSD; enhanced post-Phase-8)

**Goal:** Connect the existing `purchase_files` table to upload, list, and download file attachments (PDF/DOCX/XLSX/images) stored as PostgreSQL bytea.

**Requirements:** FILES-01, FILES-02, FILES-03, FILES-04, FILES-05, FILES-06, FILES-07

**Dependencies:** Phase 1 (purchase must exist before files can be attached)

**Enhancements delivered after initial completion:**
- SHA-256 deduplication (commit 585a3cd)
- Typed upload slots: Договор / Акт / УПД / Платёжка (commit 209941c)
- 409 on duplicate upload; auto-deactivate older file of same type (commit 0d98a90)

**Success Criteria:**
1. `POST /api/purchases/{id}/files` with a valid PDF returns HTTP 201 and a metadata JSON; the row appears in `purchase_files`.
2. `POST /api/purchases/{id}/files` with an unsupported MIME type (e.g., `.exe`) returns HTTP 415.
3. `GET /api/purchases/{id}/files` returns metadata list without `file_data` blob in the response body.
4. `GET /api/purchases/{id}/files/{file_id}` streams the file with `Content-Disposition: attachment` header and the original filename.
5. A Viewer can upload and download files; attempting `DELETE` as a Viewer returns HTTP 403.

---

### Phase 4: Contract Registry ✅ COMPLETED (pre-GSD; heavily enhanced post-Phase-8)

**Goal:** Extend the contract registry with three contract types and enforce spending ceilings for framework-limited contracts.

**Requirements:** CONTRACT-01, CONTRACT-02, CONTRACT-03, CONTRACT-04, CONTRACT-05, CONTRACT-06, CONTRACT-07, BUDGET-06

**Dependencies:** Phase 1 (purchase-to-contract linkage requires the purchase model); Phase 2 (budget check logic is reused for contract ceiling check)

**Enhancements delivered after initial completion:**
- ContractsView full redesign: row-click navigation, product search, filtered dropdowns
- Export as ZIP archive
- Contract import from PDF / Excel / Word with drag-and-drop + FileDropZone component (commit 43eb646, be7e629)

**Success Criteria:**
1. A contract created with `contract_type = framework-limited` and `max_amount = 500000` prevents a linked purchase from being saved when `current_amount` would exceed 500 000 ₽ for Manager/Viewer.
2. A framework-limited contract at 92% utilization shows a warning badge in the contract list and in the purchase form when that contract is selected.
3. `current_amount` for any contract type equals the live sum of linked purchases' `planned_total_price`, verified by adding a purchase and refreshing.
4. Contract list can be filtered by `contract_type`, contractor, and subsidy simultaneously.
5. One-time contracts display a single linked purchase reference; framework contracts display a count of linked purchases.

---

### Phase 5: Export / Import Excel ✅ COMPLETED (pre-GSD; enhanced post-Phase-8)

**Goal:** Enable one-click Excel export in GoodsService format and payment import from Scroller-format CSV/xlsx files.

**Requirements:** EXPORT-01, EXPORT-02, EXPORT-03, EXPORT-04, EXPORT-05, EXPORT-06

**Dependencies:** Phase 1 (all purchase fields must exist for complete export); Phase 2 (FEO category path required in export columns)

**Enhancements delivered after initial completion:**
- Contract import from PDF / Excel / Word with drag-and-drop (commit 43eb646)

**Success Criteria:**
1. `GET /api/purchases/export?subsidy_id=7&year=2026` returns a valid `.xlsx` file with column headers matching the GoodsService sheet template; file opens in Excel without errors.
2. All 390 ФАДМ_2026 purchases appear in the export for `subsidy_id=7`.
3. A Scroller-format `.xlsx` upload to `POST /api/payments/import` returns `{imported, skipped, errors}` JSON; rows with unmatched contract numbers appear in `errors`, not as server errors.
4. After a successful import, affected purchases have updated `payment_amount` and `payment_doc_number` values in the database.
5. The import UI shows a preview summary (N imported / M skipped / K errors) and requires explicit confirmation before applying.

---

### Phase 6: Analytics + Budget History ✅ COMPLETED

**Goal:** Surface budget change history from the existing `budget_history` table and add FEO drill-down analytics.

**Requirements:** BUDGET-07, BUDGET-08, BUDGET-09

**Dependencies:** Phase 2 (budget events must be generated before history can be displayed); Phase 1 (purchase amount changes must be trackable)

**Status:**
- Dashboard KPIs + charts: done
- BudgetDrillDownDialog FEO drill-down: done (all 3 levels verified)
- `budget_history` write-on-change (purchase + subsidy): done (plan 06-01)
- `GET /api/subsidies/{id}/history` paginated endpoint: done (plan 06-02)
- Budget history timeline/modal in subsidy detail view: done (plan 06-03)

**Plans:** 3 plans (3/3 complete)

Plans:
- [x] 06-01-PLAN.md — BudgetHistory model + write hooks in update_purchase / create_purchase / update_subsidy
- [x] 06-02-PLAN.md — BudgetHistoryItemOut schema + GET /api/subsidies/{id}/history paginated endpoint
- [x] 06-03-PLAN.md — BudgetHistoryDialog.vue component + wire into SubsidiesView.vue

**Success Criteria:**
1. Every save of a purchase that changes `planned_total_price` writes a row to `budget_history` with correct `old_value`, `new_value`, `changed_by`, `changed_at`.
2. Every change to a subsidy's `limit` also writes to `budget_history`.
3. `GET /api/subsidies/{id}/history` returns paginated history records in descending chronological order.
4. The subsidy detail view shows a budget history timeline/modal listing all changes with timestamps and user attribution.
5. The existing BudgetDrillDownDialog in the dashboard loads FEO drill-down data correctly for all three levels without errors.

---

### Phase 7: Roles + Wishes Workflow ✅ COMPLETED

**Goal:** Enforce role-based navigation and API access, and implement the full Wishes lifecycle from employee submission to purchase conversion.

**Requirements:** ROLES-01, ROLES-02, ROLES-03, ROLES-04, ROLES-05, ROLES-06, WISHES-01, WISHES-02, WISHES-03, WISHES-04, WISHES-05, WISHES-06, WISHES-07

**Dependencies:** Phase 1 (purchase creation required for wish conversion); all previous phases (roles protect all previously built endpoints)

**Status:**
- Hierarchy editor, departments, task delegation: done
- Multi-org membership (UserOrganization model, org switching): done
- `org_admin` role fix (commit a5bf274): done
- Tasks BFF endpoint + review status: done
- Wishes lifecycle (submit → approve → convert): done (изначальный flow в 07-02/07-03, расширен в Phase 13 до канбана авто-распределения)
- "Мои заявки" / "Заявки сотрудников" views: done (WishesView.vue + role-based вкладки)

**Plans:** 5/5 plans complete

Plans:
- [x] 07-01-PLAN.md — Wish model + Alembic migration + service_note columns + wishes router scaffold
- [x] 07-02-PLAN.md — Wishes API full CRUD + transitions + employee purchase filter (D-13)
- [x] 07-03-PLAN.md — WishesView.vue + router + AppBar navigation updates
- [x] 07-04-PLAN.md — Chat notification hooks + ChatRoom creation + executor reassignment hierarchy validation
- [x] 07-05-PLAN.md — Backend role gating: require_role on subsidies/contracts/payments/feo/users (ROLES-03)

**Success Criteria:**
1. Logging in as a Viewer shows only "Мои заявки" in the sidebar; direct navigation to `/subsidies` redirects to the Viewer's default page.
2. A Manager's session cannot reach `/api/wishes/{id}/reject` — returns HTTP 403 is NOT the expected result; Manager CAN approve/reject. A Viewer hitting `DELETE /api/purchases/{id}/files/{file_id}` returns HTTP 403.
3. A Viewer creates a Wish, submits it; the wish appears in the Manager's "Заявки сотрудников" view with status `submitted`.
4. A Manager approves the wish; Admin converts it to a purchase — the resulting purchase has the wish's title and `wishes.purchase_id` is set to the new purchase ID.
5. All existing API endpoints return HTTP 403 (not 401) when accessed by a role without permission, confirming server-side enforcement independent of the frontend.

---

### Phase 8: Торговые площадки + КП email + E2E ✅ COMPLETED (2026-03-20)

**Goal:** Реализовать n8n workflow для Росэлторг.Бизнес с token check и выбором типа процедуры, добавить test mode в Фабрикант workflow, настроить E2E тесты на ошибочные сценарии публикаций и SMTP endpoint.

**Requirements:** PUB-01, PUB-02, PUB-03, PUB-04, PUB-05, PUB-06, PUB-07, PUB-08, PUB-09, PUB-10

**Depends on:** Phase 7
**Plans:** 4/4 plans executed

Plans:
- [x] 08-01-PLAN.md — Backend: procedure_type в PublishRequest + publications.py payload
- [x] 08-02-PLAN.md — n8n: roseltorg_publish.json workflow + fabrikant test mode
- [x] 08-03-PLAN.md — Frontend: dropdown типа процедуры в диалоге публикации
- [x] 08-04-PLAN.md — E2E: 12-publications.spec.ts (4 теста с mock callback)

**Note:** Post-completion, n8n was removed in favour of direct API calls to Фабрикант / Росэлторг (commit 265c68e).

---

### Phase 9: Внутренний чат с уведомлениями ✅ COMPLETED

**Goal:** Реализовать встроенный мессенджер в CRM — аналог Telegram. Личные сообщения, групповые чаты, уведомления в реальном времени. Общение только между пользователями, занесёнными в персонал системы.

**Requirements:** CHAT-01, CHAT-02, CHAT-03, CHAT-04, CHAT-05, CHAT-06, CHAT-07, CHAT-08, CHAT-09, CHAT-10

**Dependencies:** Phase 7 (user/role system must exist; only staff users can participate)

**Plans:** 5/5 plans complete

Plans:
- [x] 09-01-PLAN.md — DB models: ChatRoom, ChatParticipant, ChatMessage, MessageRead
- [x] 09-02-PLAN.md — ConnectionManager + nginx WebSocket proxy config
- [x] 09-03-PLAN.md — Backend REST + WS API (chat.py router) + /tasks/badges extension
- [x] 09-04-PLAN.md — Frontend: ChatView.vue + useChat.ts composable + Vue router entry
- [x] 09-05-PLAN.md — AppBar: chat nav item + badge + WS/polling integration

**Success Criteria:**
1. Пользователь может открыть чат, выбрать другого сотрудника из списка персонала и отправить сообщение — оно появляется у получателя в реальном времени без перезагрузки страницы.
2. Групповой чат: пользователь создаёт беседу, добавляет нескольких участников (только из персонала), отправляет сообщение — все участники видят его.
3. Непрочитанные сообщения отображаются счётчиком в навигационной панели; после открытия чата счётчик сбрасывается.
4. Список чатов показывает последнее сообщение, время и количество непрочитанных — аналогично Telegram.
5. Медиафайлы: пользователь отправляет изображение или файл — оно отображается в чате, скачивается по клику.

### Phase 10: Chat Telegram-style UI

**Goal:** Telegram-like chat UX: fix real-time message delivery (WS still requires refresh), sticky chat header, dual-mode search (in-chat + across chats), overall UI polish.
**Requirements**: CHAT-UI-01 (real-time delivery), CHAT-UI-02 (sticky header), CHAT-UI-03 (dual-mode search), CHAT-UI-04 (Telegram-like polish)
**Depends on:** Phase 9
**Plans:** 3/4 plans executed

Plans:
- [x] 10-01-PLAN.md — Real-time WS delivery fix (no refresh required)
- [x] 10-02-PLAN.md — Sticky chat header
- [x] 10-03-PLAN.md — Dual-mode search (in-chat + across chats)
- [ ] 10-04-PLAN.md — AppBar chat integration (nav item + badge + WS/polling)

### Phase 11: Fix task display per-user org filtering — badges, org selector, task scoping

**Goal:** Fix badge counters, org selector, and task list scoping for per-user multi-org context
**Requirements**: TASK-FILTER-01, TASK-FILTER-02, TASK-FILTER-03
**Depends on:** Phase 10
**Plans:** 1/1 plans complete

Plans:
- [x] 11-01-PLAN.md — Backend org_id filter on /badges + frontend filteredGeneralTasks, zero-task org hide, localStorage badge sync

---

### Phase 12: Plan-Graph FEO Integration

**Goal:** Connect FEO line items to the purchase plan-graph: FEO planned amounts become the "Plan-schedule" baseline in the pipeline dashboard, purchases are matched to FEO items when created, residual budget is tracked per FEO item, each plan-graph iteration is versioned with dates for export/signing, and a printable plan-graph form can be attached to each subsidy.

**Requirements:** PLANGRAPH-01, PLANGRAPH-02, PLANGRAPH-03, PLANGRAPH-04, PLANGRAPH-05, PLANGRAPH-06, PLANGRAPH-07, PLANGRAPH-08

**Depends on:** Phase 2 (FEO model), Phase 11 (stable dashboard)

**Plans:** 0/4 plans (not executed)

**Success Criteria:**
1. Dashboard pipeline "План-график" bar shows the sum of FEO item planned costs even before any purchases exist.
2. When a purchase is saved with a FEO category, the system finds the matching FEO item and links them (by name similarity or manual mapping).
3. If purchase actual amount < FEO planned amount, the FEO item shows as a folder with: (a) the purchase, (b) a residual row = planned − actual.
4. If a new purchase would exceed the remaining FEO item budget, a warning is shown and non-admin users are blocked.
5. Each time the plan-graph is changed (purchase added/removed/amount changed), a new version is recorded with date and author.
6. Admin can export the plan-graph as a formatted document (Excel/PDF) and attach it to a subsidy.

---

### Post-Phase 11: Фидбек Голичков + Суперадмин (апрель 2026) ✅ DELIVERED

Features delivered from user feedback documents, outside GSD phase tracking:

| Feature | Commit |
|---------|--------|
| Hierarchy-based task/purchase filtering (_get_visible_user_ids) | 36625ed |
| org-summary counts respect role visibility | 36625ed |
| Document buttons (ТЗ/Договор/Лист) open to all roles | 36625ed |
| can_publish permission (User model + migration + full pipeline) | 36625ed |
| Clickable org stat badges → navigate to tasks/purchases | 36625ed |
| Contract number: single confirm on click, not per-keystroke | 36625ed |
| "Тип товара" → "Товар / Услуга" label | 36625ed |
| "Россия" default — persistent hint | 36625ed |
| autodeploy.sh: rebuild backend, not just restart | 6a0d0a0 |
| Superadmin sees all tasks/purchases when selecting org | 57386cd |
| org-summary excludes done/cancelled tasks, paid purchases | 57386cd |
| Kanban: collapsible "Архив" column | 57386cd |
| Kanban: subsidy filter dropdown | 57386cd |
| Org card stats: larger font, readable | 57386cd |
| Draggable dashboard widgets (grid-layout-plus) | c0ba75f |
| Visual enhancements (glassmorphism, animations, transitions) | 2254e1f |
| Markitdown document import pipeline | e6c147f |

### Phase 13: Заявки v3: авторасспределение позиций по закупкам, drag-drop перекидывание товаров между закупками, одобрение распределения и автосоздание N закупок, генерация служебной записки ✅ COMPLETED (2026-04-23)

**Goal:** Turn WishesView into a kanban auto-distribution tool: user creates a wish with items, system groups items into columns by `product.category` (+ «Не определено» column), user can drag-drop between columns within the wish, then approves all-or-nothing → N purchases created in status=`wishes`; downloadable служебная записка generated directly from a wish.
**Requirements**: D-01..D-08 from 13-CONTEXT.md (fixed decisions from 2026-04-20 discussion)
**Depends on:** Phase 15 (PurchaseItemsEditor extraction — done), Phase 16 (router decomposition — in progress; does not block)
**Plans:** 7/7 plans complete

Plans:
- [x] 13-01-product-category-not-null-PLAN.md — Alembic migration to backfill NULL → 'Прочее' and flip products.category NOT NULL; pytest for 422 on create without category
- [x] 13-02-wish-distribution-approve-PLAN.md — WishItem.target_column_key column + PATCH /items/{iid} + POST /approve-distribution atomic transaction + pytest rollback verification
- [x] 13-03-wish-service-note-endpoint-PLAN.md — New router wish_documents.py exposing GET /api/wishes/{id}/documents/service_note using existing service_note.docx template
- [x] 13-04-advanced-product-selector-category-required-PLAN.md — Frontend validation: required category in AdvancedProductSelector + PurchaseItemsEditor full-product dialog
- [x] 13-05-wish-distribution-kanban-PLAN.md — WishDistributionKanban + WishDistributionCard components with vuedraggable; wire into WishesView with category enrichment + approve flow
- [x] 13-06-wish-service-note-button-PLAN.md — "Скачать служебную записку" button + initiator picker dialog in WishesView
- [x] 13-07-e2e-and-integration-PLAN.md — Playwright spec e2e/19-wishes-kanban.spec.ts covering happy path + DnD + approve + service note + category validation

**Wave structure (revised 2026-04-20 after checker blocker 1):**
- Wave 1 (parallel): 13-01 (backend migration — products.category NOT NULL), 13-04 (frontend category validation)
- Wave 2: 13-02 (backend approve endpoint + wish_items.target_column_key — migration chains on 13-01, so MUST follow Wave 1)
- Wave 3 (parallel): 13-03 (backend service_note endpoint — after 13-02 for wish shape), 13-05 (kanban UI — depends on 13-02 + 13-04)
- Wave 4: 13-06 (service note button — depends on 13-03)
- Wave 5: 13-07 (E2E — depends on all prior plans)

**Success Criteria** (from 13-CONTEXT.md):
1. При открытии заявки в WishesView видно канбан с N+1 колонками (категории + «Не определено»)
2. Drag карточки между колонками обновляет target (опт-PATCH), visual reorder мгновенный
3. Кнопка «Одобрить» создаёт N закупок за один transaction, status=wishes; заявка → status='approved', read-only
4. `category` в форме создания товара в `AdvancedProductSelector` — обязательное поле с валидацией
5. Кнопка «Скачать служебную записку» в WishesView открывает диалог выбора инициатора и генерит docx
6. E2E: создание заявки → распределение → DnD → одобрение → верификация N закупок в БД

### Phase 14: Risk Radar — альтернативный визуал Dashboard (Neon Telemetry стиль)

**Goal:** Deliver a Neon Telemetry "mission control" variant of the Dashboard at /dashboard/radar — same data as classic DashboardView, reprojected as 6 weighted risk scores + polar radar + alerts ticker, both Vuetify themes first-class, without modifying DashboardView.vue.
**Requirements**: RISK-RADAR-01..10 (informal — Phase 14 has no ROADMAP REQ-IDs; see 14-UI-SPEC.md + 14-CONTEXT.md for the authoritative contract)
**Depends on:** None (Phase 14 is independent of Phase 12/13 — reuses existing /api/dashboard/charts)
**Plans:** 3/4 plans executed

Plans:
- [x] 14-01-PLAN.md — Foundation: router entry + useDashboardMode + useRiskScores composables (Wave 1, parallel with 14-02)
- [x] 14-02-PLAN.md — Reusable components: RiskMetricCard + AlertsTicker (Wave 1, parallel with 14-01)
- [x] 14-03-PLAN.md — RiskRadarView.vue assembly with polar + radial charts, 2×3 grid, ticker, dual-theme CSS tokens (Wave 2)
- [ ] 14-04-PLAN.md — Polish + automated audit + human UAT on 4 theme×mode combos (Wave 3, checkpoint)

### Phase 15: Reusable Purchase Items Editor — унификация формы позиций в «Новом заказе» и «Заявке» ✅ COMPLETED (2026-04-19)

**Goal:** Extract the full position-editor block (inline table + products autocomplete with photo tooltip, quick/full product dialogs with photo upload, Excel import with drag-and-drop column mapping, smart AI import, FileDropZone) from CreateOrderView.vue into a reusable component `<PurchaseItemsEditor v-model="items" :supports_photos :supports_files :allowed_item_types />`. Wire it into both CreateOrderView.vue (replacing ~2000 lines of inline logic) and WishesView.vue Section 2 "Позиции" so Заявка gets full parity with Новый заказ — same products DB, same photos, same imports.
**Requirements**: ITEMS-EDITOR-01..08 (informal — see 15-CONTEXT.md for the authoritative contract)
**Depends on:** None (pure refactor)
**Unblocks:** Phase 13 (Заявки v3 auto-redistribution reuses the same editor)
**Plans:** 5/5 plans complete

Plans:
- [x] 15-01-PLAN.md — Extract PurchaseItemsEditor.vue component
- [x] 15-02-PLAN.md — Delete dead OrderProductsTable.vue
- [x] 15-03-PLAN.md — Wire into CreateOrderView (-1425 lines)
- [x] 15-04-PLAN.md — Wire into WishesView Section 2 (-100 lines)
- [x] 15-05-PLAN.md — E2E smoke spec + closure (3/3 pass on deploy)

---

### Phase 16: Refactor Monoliths — рефакторить код, чтобы не было огромного файла на 4000 строк ✅ COMPLETED

**Directory:** `.planning/phases/16-refactor-monoliths/`

**Goal:** Разрезать накопившиеся монолиты на тематические модули по принципу «один процесс — один модуль». Правило нарушено за фазы 1-7: новые фичи лились в существующие роутеры/views без выделения. Результат — 3 файла на ~7 000 строк в сумме: тяжело читать, трудно тестировать, конфликты в git при параллельной работе, и (как показала история Phase 11) баги накапливаются в роли оракулов-переростков.

**Что декомпозировать:**

1. **`backend/app/routers/purchases.py` (3200 строк):**
   - `purchases.py` — только CRUD (list, get, create, update, delete)
   - `purchase_transitions.py` — workflow status transitions (planned→confirmed→…→paid)
   - `purchase_budget.py` — `_check_budget` + FEO cap validation
   - `purchase_members.py` — participants + consent flow
   - `purchase_files.py` уже отдельно — оставить как есть
   - `purchase_export.py` — Excel export (перенести из purchases.py)

2. **`backend/app/routers/tasks.py` (1639 строк):**
   - `tasks.py` — только CRUD + list
   - `task_visibility.py` — `_get_visible_user_ids` + related helpers
   - `task_badges.py` — `/badges` + `org-summary` endpoints
   - `task_delegation.py` — subtasks, consent, assignee management
   - `task_comments.py` — comments + mentions

3. **`frontend/src/views/MyTasksView.vue` (2155 строк):**
   - `MyTasksView.vue` — оркестратор (router, state, api calls)
   - `components/OrgSelector.vue` — карточки орг + «Все организации»
   - `components/TasksTable.vue` + `TasksKanban.vue` — вкладка Задачи
   - `components/PurchasesTable.vue` + `PurchasesKanban.vue` — вкладка Закупки
   - `components/OrgSummaryBar.vue` — счётчики + badges

**Requirements:** REFACTOR-01..12 (TBD during planning)
**Depends on:** Phase 15 (demonstrates the extraction pattern)
**Unblocks:** Phase 12, 13, параллельная разработка, снижение когнитивной нагрузки

**Non-goals (не в этой фазе):**
- Изменения функциональности — чистый рефакторинг
- Изменения DB схемы
- Изменения API контрактов (имена endpoints/URL-ов остаются)
- Миграция stack'а или библиотек

**Success Criteria:**
1. Каждый новый модуль ≤ 800 строк. Ни одного файла ≥ 1000 строк после фазы.
2. Все существующие E2E тесты (67+3) проходят без изменений — 0 regression.
3. Backend импорты: `from app.routers import purchases, purchase_transitions, ...` работают; `app/main.py` монтирует все роутеры.
4. Frontend билд зелёный; MyTasksView рендерится идентично визуально (до/после — скриншот-diff).
5. Каждый коммит рефакторинга атомарный: «extract X from Y» — удалил здесь, добавил там, build зелёный.

**Plans:** 15/15 plans complete (16-15-UAT.md pass)

Plans:
- [x] 16-01..16-15 — декомпозиция purchases.py (3200→<800) + tasks.py (1639→<800) + MyTasksView.vue (2155→<800); backend тесты + E2E smoke зелёные

---

### Phase 17: Permission System — матрица ролей + индивидуальные override'ы

**Directory:** `.planning/phases/17-permission-system-override/`

**Goal:** Заменить хардкод роль→вкладка на конфигурируемую матрицу. Админ задаёт доступные вкладки per-role, и отдельно умеет точечно выдавать/забирать доступ конкретному пользователю (галочки). При override роль в карточке пользователя превращается в `Индивидуально`.

**Контекст (из фидбека 2026-04-21):**
- Любарец (employee) видит вкладку «Персонал», но редактировать её не может — значит и показывать не нужно. Сейчас правило `allNavShortcuts[].roles` и `menuItems[].roles` хардкодом в `AppBar.vue:373-471`.
- По умолчанию новый user создаётся с ролью `Пользователь` (= `employee`).
- Нужна страница «Роли» (админка) + галочки в карточке пользователя.

**Scope (черновой):**
1. **Backend:**
   - Миграция: таблица `role_permissions (role_name, tab_key)` + `user_permission_overrides (user_id, tab_key, granted bool)`
   - Список `tab_key` — справочник всех вкладок (enum или seed-таблица)
   - API: `GET /api/permissions/tabs`, `GET/PUT /api/permissions/roles/{role}`, `GET/PUT /api/users/{id}/permissions`
   - `/api/users/me` возвращает effective permission list (merge role + overrides)
   - Guard в роутерах — Depends(require_tab("staff")) вместо require_role
2. **Frontend:**
   - Страница «Роли» (ADMIN_ROLES) — список ролей × список вкладок, галочки
   - В карточке пользователя секция «Доступ» — роль + индивидуальные галочки (при любом override роль → `Индивидуально`)
   - `AppBar.vue` читает effective tabs из `/users/me` вместо хардкода `.roles`

**Success Criteria:**
1. Админ может убрать «Персонал» у employee-ролей через UI — изменение применяется без передеплоя
2. Индивидуальный override для одного user сохраняется и переживает смену роли (пока override не снят)
3. Не видит вкладку в сайдбаре = не может достучаться до API (backend guard)
4. Миграция seed'ит текущие маппинги `ADMIN_ROLES/MANAGER_ROLES/ALL_ROLES` → нулевая регрессия для существующих пользователей

**Plans:** 5/9 plans executed
- [x] 17-01-PLAN.md - permission models + alembic migration + seed from hardcode + can_publish data migration (D-02/05/07/08)
- [x] 17-02-PLAN.md - Wave 0 validation: conftest fixtures + 5 backend test files + e2e/20-permissions.spec.ts scaffolding
- [x] 17-03-PLAN.md - require_tab/require_action factories + get_effective_tabs + /users/me permissions field (D-01b/02/08)
- [ ] 17-04-PLAN.md - migrate 78 require_role call-sites to require_tab/require_action across 21 routers (D-01b/06)
- [x] 17-05-PLAN.md - permissions router (CRUD matrix + overrides) + self-lockout + superadmin filter on list_users (D-03/05/09)
- [x] 17-06-PLAN.md - Pinia stores/auth.ts + AppBar nav filter by hasTab + login/org-switch wiring (D-01a)
- [ ] 17-07-PLAN.md - AdminRolesView.vue matrix 5xN with debounced save + self-lockout disable + checkpoint (D-03/05)
- [ ] 17-08-PLAN.md - UserPermissionsSection.vue (per-org overrides + Individual badge) integrated into StaffView (D-04/08)
- [ ] 17-09-PLAN.md - router guards meta.tab_key + E2E regression + phase sign-off checkpoint (D-01a/05/09)

---

### Phase 18: Staff Directory — справочник сотрудников внутри своих организаций

**Directory:** `.planning/phases/18-staff-directory/` (TBD)

**Goal:** Read-only справочник «Сотрудники»: ФИО, должность, телефон, email — виден всем сотрудникам внутри своих организаций. Отдельная вкладка, отличная от админской «Персонал» (где идёт редактирование).

**Контекст (из фидбека 2026-04-21):**
- Сейчас вкладка «Персонал» (`/staff`) — только для ADMIN_ROLES, с редактированием. Обычный сотрудник не видит контакты коллег.
- Нужен второй read-only экран «Сотрудники» / «Контакты» с фильтром по `org_id ∈ my_org_ids`.

**Scope:**
1. **Backend:** `GET /api/staff-directory` — возвращает `[{id, full_name, position, phone, email, org_name, photo_url}]` отфильтровано по `get_org_filter(current_user)`
2. **Frontend:** `views/StaffDirectoryView.vue` — таблица + поиск + клик на строку → mini-card с контактами; роут `/directory` доступен всем ролям (ALL_ROLES)
3. **Navigation:** пункт меню «Сотрудники» в AppBar

**Success Criteria:**
1. Employee видит всех коллег из всех своих организаций (не только primary), но не видит сотрудников других организаций
2. Поиск по ФИО/должности/телефону/email
3. Нет кнопок редактирования — только read-only
4. Мобильная адаптация — карточный вид на XS

**Plans:** TBD
- [ ] TBD

---

### Post-Phase 8: Untracked Additional Work ✅ DELIVERED

Features delivered after Phase 8 completion, outside GSD tracking:

| Feature | Commit(s) |
|---------|-----------|
| n8n removed — direct API calls for Фабрикант / Росэлторг | 265c68e |
| SMTP configured (z@vsks.ru) | — |
| PWA + mobile navigation | 1f5b9e2 |
| Telegram integration (reply button, inline consent) | 5c9008e, 202f2e8 |
| org_admin role fix | a5bf274 |
| SHA-256 file deduplication | 585a3cd |
| Typed upload slots (Договор / Акт / УПД / Платёжка) + active/inactive toggle | 209941c |
| Duplicate file upload → 409 + auto-deactivate older file of same type | 0d98a90 |
| Contract import from PDF / Excel / Word with drag-and-drop | 43eb646 |
| Universal FileDropZone component | be7e629 |
| Purchase member consent + notifications | — |
| Review status on tasks | — |
| Tasks BFF endpoint (/api/tasks/my) | — |
| Dark mode fixes across multiple components | — |
| Draggable columns (order persisted to localStorage) | — |
