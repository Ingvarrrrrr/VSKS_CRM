# ROADMAP.md — VSKS_CRM

## Overview

7 phases | 57 requirements | Brownfield (existing codebase: auth, CRUD, dashboard, SubsidiesView, 390 purchases, 612 contractors)

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

### Phase 7: Roles + Wishes Workflow ⚠️ PARTIAL

**Goal:** Enforce role-based navigation and API access, and implement the full Wishes lifecycle from employee submission to purchase conversion.

**Requirements:** ROLES-01, ROLES-02, ROLES-03, ROLES-04, ROLES-05, ROLES-06, WISHES-01, WISHES-02, WISHES-03, WISHES-04, WISHES-05, WISHES-06, WISHES-07

**Dependencies:** Phase 1 (purchase creation required for wish conversion); all previous phases (roles protect all previously built endpoints)

**Status:**
- Hierarchy editor, departments, task delegation: done
- Multi-org membership (UserOrganization model, org switching): done
- `org_admin` role fix (commit a5bf274): done
- Tasks BFF endpoint + review status: done
- Wishes lifecycle (submit → approve → convert): NOT done
- "Мои заявки" / "Заявки сотрудников" views: NOT done

**Plans:** 5 plans

Plans:
- [ ] 07-01-PLAN.md — Wish model + Alembic migration + service_note columns + wishes router scaffold
- [ ] 07-02-PLAN.md — Wishes API full CRUD + transitions + employee purchase filter (D-13)
- [ ] 07-03-PLAN.md — WishesView.vue + router + AppBar navigation updates
- [ ] 07-04-PLAN.md — Chat notification hooks + ChatRoom creation + executor reassignment hierarchy validation
- [ ] 07-05-PLAN.md — Backend role gating: require_role on subsidies/contracts/payments/feo/users (ROLES-03)

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

### Phase 9: Внутренний чат с уведомлениями ○ IN PROGRESS

**Goal:** Реализовать встроенный мессенджер в CRM — аналог Telegram. Личные сообщения, групповые чаты, уведомления в реальном времени. Общение только между пользователями, занесёнными в персонал системы.

**Requirements:** CHAT-01, CHAT-02, CHAT-03, CHAT-04, CHAT-05, CHAT-06, CHAT-07, CHAT-08, CHAT-09, CHAT-10

**Dependencies:** Phase 7 (user/role system must exist; only staff users can participate)

**Plans:** 5/5 plans complete

Plans:
- [x] 09-01-PLAN.md — DB models: ChatRoom, ChatParticipant, ChatMessage, MessageRead
- [x] 09-02-PLAN.md — ConnectionManager + nginx WebSocket proxy config
- [x] 09-03-PLAN.md — Backend REST + WS API (chat.py router) + /tasks/badges extension
- [x] 09-04-PLAN.md — Frontend: ChatView.vue + useChat.ts composable + Vue router entry
- [ ] 09-05-PLAN.md — AppBar: chat nav item + badge + WS/polling integration

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
- [ ] TBD (run /gsd:plan-phase 10 to break down)

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
