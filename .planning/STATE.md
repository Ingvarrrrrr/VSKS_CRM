---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Ready to plan
last_updated: "2026-05-07T20:00:00.000Z"
progress:
  total_phases: 20
  completed_phases: 15
  total_plans: 80
  completed_plans: 78
---

# STATE.md — VSKS_CRM

## Current Position

Phase: 24 ✅ (завершена)
Next action: UAT реформы авансовых отчётов (создать Ростелеком 12 этапов + 2 чека от разных ИП → проверить multi_contractor_label + reimbursement_user + FEO-drill в pipeline). Затем — право `purchase.transition.skip_validation` (новый action) и backend mismatch /dashboard/ vs /charts.
Resume file: None

## 2026-05-07 — Phase 24 + drill-down + реформа авансовых

Push `c5ed69a` (последний из 24 коммитов): этапы рамочного, FEO-drill в pipeline, реформа авансовых отчётов в 3 фазы (reimbursement_user → per-item contractor → multi_contractor_label).

Detailed log: `/c/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Sessions/2026-05-07_VSKS_CRM.md`.

### Инциденты
- 2× OOM build на проде после крупных frontend refactor'ов (`81a5267`, `307290f`) → revert + атомарные правки. Lesson зафиксирован.
- alembic chain сломан, `check_schema.py --apply` авто-добавляет колонки на старте контейнера.

### Bundle deployment chain (для контроля OOM)
`8ea172f→DpY8cZqE→OOM→DWu4YuSF→B6MSF_sA→CWprrQSO→DFqZxfNU→BjOYCtYV→D1ECJ3n0→BlpoywjK→BoMULp2O→BQnejltI→Drz-nu6d`

## 2026-05-05 — Triage 3 (фидбек 5 мая, docx)

Push `89514eb` — 9 правок одним коммитом, applied/verified на проде:

1. **check_schema asyncpg multi-statement bug** — DROP+ADD одним `text()` падал PostgresSyntaxError; теперь два отдельных execute. Cascade FK `payments.purchase_id` стоял NO ACTION с момента a273f8c (4+ дня) — фикс применён вручную SQL + код корректен на следующий деплой.
2. **`/departments/{id}/members` UNION** — раньше показывал только из `department_members`; теперь UNION с `user_organizations.dept_id` → Цыганов виден в depts 3, 17, 18 (подтверждено API). `add_member` больше НЕ удаляет другие отделы той же org (раньше «one dept per org» сносил multi-dept).
3. **PATCH `/purchases/{pid}`** — НОВЫЙ endpoint. Phase 26 autosave стрелял PATCH, но его не было → 405 → autosaveState='error' silently. Поэтому пропадал контрагент в #525. PATCHABLE whitelist + partial body.
4. **Тогл «Адрес доставки/Место оказания услуг»** в карточке закупки (v-btn-toggle над AddressAutocomplete). Новое поле `purchases.delivery_location_kind` + schema/PATCHABLE.
5. **Receipt block для advance method** — раньше был только в `formMode='advance_report'` (/advance-reports). Теперь и для обычной закупки с `purchase_method='advance'`. loadReceipts() расширен.
6. **Transitions для авансового** — `FIELD_LABELS` подменяются: `contract_date` → «Дата документа основания (чек/УПД)», `contract_number` → «№». Хинт без служебных слов.
7. **`lookup-inn` НЕ дефолтит «Юридическое лицо»** для 12-знач ИНН без ОГРН → None, пользователь сам выбирает.
8. **AddressAutocomplete defaults** — «По месту нахождения подрядчика» (вместо «На территории Исполнителя») + ownOrgAddress prop + customerAddress.
9. **focusout-handler** — flush autosave немедленно при blur поля (помимо debounce 1500ms). Document capture-phase listener.

UAT pending: пользователь проверяет на проде (Ctrl+F5 → /orders, /dashboard). Ошибок в логах backend кроме тестовой PATCH с FK violation — нет.

Recently closed:

- Phase 22 — Импорт банковских выписок (8/8 planов, commits 0ec6c22..6af20a8); парсер xlsx (header-based mapping, 20 групп multi-row split, regex contract/КБК/дата); matcher по ИНН+contract_number; auto-paid при SUM≥порога И matched_confirmed=true; UI /payments/import + /payments/registry + PaymentsBlock в карточке закупки; 7 backend endpoints + permission seed (`payment_registry` tab + 3 actions)
- Phase 21 — Авансовые отчёты + чеки + ФНС (deployed 2026-04-26)
- Phase 17 — Permission System Override (9/9 planов, commits 1622167, f733aca + per-plan commits; 9 decisions D-01..D-09 delivered)
- Phase 13 — Заявки v3 канбан + split purchase kanban (7/7 планов, commits 9ae0202, c2312f8, f40546c, d1b3cb9, fcbed67)
- Phase 16 — Refactor monoliths (15/15, 16-15-UAT pass)
- Phase 15 — PurchaseItemsEditor extraction (5/5)

- **Milestone:** v1.0
- **Last Completed Phase:** 17 → 16 → 13 (в порядке закрытия)
- **Profile:** balanced (Opus plans, Sonnet executes)

## Status

- ✅ Complete (18): Phases 1–9, 10, 11, 13, 14, 15, 16, 17, 21, 22
- ⏳ Not started (2): Phase 12 (4 плана ready), Phase 18 Staff Directory (TBD)
- Post-phase feedback work: ✅ Delivered (Голичков-3, Суперадмин-1, Суперадмин-2, Суперадмин-3)

## Recent Activity (April–May 2026)

- 2026-05-04: **Карточка сотрудника — 3 фикса** (`4df1a86`). (1) Фото сотрудника в editDialog StaffView: вертикальный прямоугольник 4:5 (160×200 превью, 240×300 storage), border-radius 12px, новые admin endpoints `GET/PUT/DELETE /users/{user_id}/photo` (require_tab('staff')); `ProfilePhotoUpload.vue` расширен props `format='circle'|'rectangle'` + `userId?` (AppBar остаётся круглым). (2) Кнопка `mdi-delete` у каждой строки `allOrgEntries` в editDialog → новый `DELETE /api/users/{uid}/org-memberships/{row_id}` (по PK строки `user_organizations`, mirror в `department_members`, снимает `user.org_id` если строк к этой org не осталось). `GET /users/{uid}/salary` теперь отдаёт `id` + `dept_id`. (3) `GET /api/hierarchy/graph` `members_map` = UNION(`department_members`, `user_organizations.dept_id`) — Цыганов в 4 отделах ВСКС теперь появляется в каждом на канвасе. UAT: открыть карточку Цыганова, удалить лишние строки, загрузить фото; проверить что на канвасе HierarchyView сотрудник появляется во всех своих отделах.
- 2026-05-04: **Approval workflow integration** — 3 коммита (`5d2414f`, `7f50475`, `fdb11c2`). (1) `SubsidiesView` диалог approver получил `<v-autocomplete>` сотрудников — выбор `user_id` обязателен, `full_name` авто-подставляется; старые записи без user_id блокируются на сохранении с warning. (2) `purchase_approvals.start_approval` теперь создаёт `Task(category="Согласование", purchase_id, due_date=approval_deadline)` + `TaskAssignee` + `ChatRoom` через `_create_assignment_chat_room` + system-message «📋 Запущено согласование» для каждого approver_user; `decide_approval` закрывает Task (approve→done, reject→cancelled), `reset_approvals` отменяет все pending. (3) `purchases.update_purchase` + `create_purchase` — `contract_price` авто-пересчёт расширен: `(is_single_contract OR is_advance) and items_sum` — раньше авансовые отчёты с `purchase_method='advance'` не пересчитывали contract_price; рамочные не затронуты. Backfill закупки #573 — открыть+сохранить.
- 2026-04-27: **Phase 22 CLOSED** — Bank Statements Import. 8/8 планов, 8 коммитов (`0ec6c22..6af20a8`) push'нуты в `claude`. Backend: 2 новые таблицы (`bank_statement_imports`, `bank_payments`), парсер xlsx (header-based mapping для разноколоночных выгрузок, 20-групп multi-row split в ScrollerHash формате, regex для contract_number/КБК/parsed_date), matching service (ИНН+contract_number), 7 endpoints, permission seed (`payment_registry` tab + 3 actions). Frontend: /payments/import (DropZone + журнал), /payments/registry + PaymentMatchDialog (ручной матчинг + confirm), PaymentsBlock в CreateOrderView (показывает N платежей закупки + источник). Auto-paid при SUM≥contract_price/planned_total_price И matched_confirmed=true. Pending: применить 2 SQL миграции на проде (alembic chain сломан).
- 2026-04-23: **Phase 17 CLOSED** — Permission System Override, 9/9 planов. 17-09: router guards migrated to `meta.tab_key` + `authStore.hasTab()` (32 routes, commit 1622167); E2E spec 20-permissions.spec.ts unskipped with 7 tests (commit f733aca). EMPLOYEE_ALLOWED removed. All 9 decisions D-01..D-09 delivered. Ready for `/gsd:verify-work 17`.
- 2026-04-23: Purchase Split Kanban — DnD-редистрибуция позиций в существующей закупке, N дочерних закупок, блокируется после статуса «Договор» (не-админам). commits: 40b9d98, 17ec94b, 6a13456, 06ef867, 60379f7, fbb6169. Bugfix цепочка: id-propagation → column width/wrap → ref-state DnD.
- 2026-04-23: Wishes edit dialog — product_id persistence в WishItem schema + 3-layer name-fallback (openEditDialog, openKanbanDialog, approve_distribution) + assignee action banners по ролям.
- 2026-04-23: Knowledge graph updated — targeted AST-refresh для 14 файлов Phase 13/15/Split scope, pruned 83 VAULT ghost nodes. Final: 1645 nodes / 4843 edges / 234 communities.
- 2026-04-23: STATE.md + ROADMAP.md sync с реальностью — Phase 7 PARTIAL→✅, Phase 13 ✅, Phase 16 "в работе"→✅.
- 2026-04-23: Phase 17 context gathered — 9 решений (D-01..D-09) через опросник. Scope = 3 уровня (nav + API + sub-actions). Override = boolean flip. Admin UI = матрица роль×вкладка. Badge = «Индивидуально». Per-org structure (role per-org + overrides per-org). Superadmin полностью невидим для не-superadmin (SaaS-сотрудник).
- 2026-04-19: Phase 16 context gathered — CONTEXT.md + DISCUSSION-LOG.md for Refactor Monoliths (faaa12d). Auto-mode picked 6 gray-area defaults: backend-first order, 6 modules for purchases.py (added items_import), 5 for tasks.py, orchestrator+5 components for MyTasksView, helpers stay in originating modules, strict URL preservation, E2E + smoke gates.
- 2026-04-19: Autodeploy hardened (2d04e4e) — ThreadingHTTPServer в webhook.py, always-restart в autodeploy.sh, /healthz endpoint. Root cause предыдущего падения: single-threaded HTTPServer завис в accept loop, systemd репортил active, но всё таймаутило. 2 дня push'ей были silently dropped.
- 2026-04-19: Phase 11 reopened+fixed — 4 UX бага на /my-tasks под employee: закупки без org/member фильтра (ce90039), flash unfiltered tasks + "Все организации" не кликалось + счётчик header считал done/cancelled (f3cf2cc).
- 2026-04-19: Phase 15 closed — PurchaseItemsEditor extracted (15-01), dead OrderProductsTable removed (15-02), wired into CreateOrderView -1425 lines (15-03), wired into WishesView -100 lines (15-04), E2E smoke spec 3/3 pass on deploy (15-05). Заявка ↔ Новый заказ parity achieved.
- 2026-04-19: Phase 14.1 post-MVP fixes — Radar nav entry (b911e75), Classic/Radar toggle in DashboardView (4a43c30), formulas info dialog (5c87c47). QA PASS WITH NOTES.
- 2026-04-19: Phase 14 UI-SPEC approved (revision 1/2, typography fix) — CONTEXT.md + DISCUSSION-LOG.md + UI-SPEC.md ready for planning
- 2026-04-19: Phase 14 context gathered (Risk Radar Neon Telemetry Dashboard)
- 2026-04-17: Superadmin-3 feedback, Wishes v2 (items+FEO+subsidy), persistent templates volume
- 2026-04-16: Superadmin-2 feedback fixes (org-aware task loading, archive column, subsidy filter)
- 2026-04-15: Golichkov-3 + Superadmin-1 feedback fixes (hierarchy filtering, can_publish, document access)
- 2026-04-14: Draggable dashboard, visual enhancements, document import
- 2026-04-12: Pipeline funnel, dashboard cards, FEO fixes

## Decisions

- Direct API for Фабрикант/Росэлторг (n8n removed)
- PostgreSQL bytea for file storage (no filesystem)
- Autodeploy: git push → webhook → docker compose build backend + frontend
- [Phase 14]: AlertsTicker uses doubledItems+translateX(-50%) for seamless CSS marquee loop without JS timers
- [Phase 14]: Stub RiskRadarView.vue created to unblock vite-plugin-pwa build (Plan 14-03 replaces it)
- [Phase 14]: RiskRadarView uses isDark-reactive hex dictionaries for ApexCharts colors (CSS vars not readable by SVG engine)
- [Phase 15]: OrderProductsTable.vue confirmed dead (only .backup.vue referenced it) — deleted to clean frontend/src/components before PurchaseItemsEditor lands
- [Phase 15]: PurchaseItemsEditor.vue: purchaseId-aware import branching — null path uses client-side row assembly from preview, set path calls pid-bound API; imap-* CSS migrated to component scoped styles; emit('items-changed') replaces direct syncContractPriceIfSingle call
- [Phase 15]: WishesView :readonly=false since dialog guard at call-site ensures only draft wishes are editable
- [Phase 15]: wishForm.items typed as any[] to accept EditorItem superset; saveWish strips helper fields with destructure map
- [Phase 15]: FEO column Branch 3 (no per-row FEO in old items table) — no #row-extra slot; feo_planned_item_id flows via v-model
- [Phase 15]: quickProductEditDialog deleted as dead code (Plan 15-03) — caller button removed with items table; PurchaseItemsEditor has own internal handler
- [Phase 16]: httpx 0.27.0 already present in requirements.txt — kept existing version
- [Phase 16]: ASGITransport (in-process) pattern for FastAPI pytest — no port conflicts, < 10s execution
- [Phase 16-05]: Extracted _create_assignment_chat_room + 5 endpoints into purchase_members.py; cleaned 3 unused imports from purchases.py
- [Phase 16-refactor-monoliths]: tasks.py at 641 lines (not 500): create/update consent logic is dense — splitting requires new service layer (16-12 candidate)
- [Phase 16-refactor-monoliths]: OrgSummaryBar includes consent banners (D-18 badges scope) enabling required line reduction
- [Phase 16-refactor-monoliths]: visibleOrgSummary computed moved to OrgSelector child — child owns its own filter logic
- [Phase 16-refactor-monoliths]: TasksTable+TasksKanban are pure-presentation components; handleUpdateTaskStatus in MyTasksView handles PATCH persistence via update-status emit
- [Phase 13-v3-drag-drop-n]: AdvancedProductSelector delegates product creation to AddProductDialog — validation applied in AddProductDialog, not inline
- [Phase 13-v3-drag-drop-n]: Category payload uses .trim() instead of || null since field is now required (matches DB NOT NULL from plan 13-01)
- [Phase 13-v3-drag-drop-n]: Backfill NULL products.category to 'Прочее' before NOT NULL constraint (D-03); downgrade reverts constraint only
- [Phase 13-v3-drag-drop-n]: ProductCreate.category required via Pydantic Field(..., min_length=1) — empty string also rejected at API layer
- [Phase 13-v3-drag-drop-n]: 409 for approved-wish edit (not 403): resource state conflict. 404 for cross-wish PATCH: item not in that wish. Explicit db.rollback() in approve-distribution for atomicity. product relationship added to WishItem for category resolution.
- [Phase 17-permission-system-override]: FK user_org_access_id (not user_id+org_id pair) per D-08 — UserOrgAccess already enforces uniqueness
- [Phase 17-permission-system-override]: publication.create NOT seeded into role_permissions — per-user override via can_publish migration (Step E)
- [Phase 17]: Wave 0 test scaffolding uses deferred imports in fixtures to prevent collection errors while Plan 17-01 models exist on disk but DB migration not yet run
- [Phase 17]: require_tab/require_action import directly from app.auth.permissions at call-sites (no jwt.py re-export needed)
- [Phase 17]: Split effective key set into tabs vs actions using PermissionTab/PermissionAction dictionary tables at /me endpoint
- [Phase 17]: Pinia auth store (stores/auth.ts) uses tab_key filter via authStore.hasTab() replacing hardcoded roles arrays in AppBar.vue; fail-open pattern on loadPermissions errors
- [Phase 17]: D-09 superadmin filter applied in 4 user-listing locations: list_users, _get_visible_user_ids, hierarchy graph, task authority; all other select(User) sites annotated superadmin-bypass-ok
- [Phase 17]: permissions.router prefix /api/permissions in constructor; org_id as Query(...) param in override endpoints; self-lockout returns 403 on admin.roles+staff keys for own role
- [Phase 17-permission-system-override]: purchases.py bulk_delete → require_tab('purchases') — no separate delete action seeded for purchases
- [Phase 17-permission-system-override]: publications.py can_publish inline check already absent; declarative require_action('publication.create') added on POST endpoint per D-06
- [Phase 17-permission-system-override]: users.py GET /users/ stays require_role(*ALL_ROLES) — 17-05 handles superadmin filter there
- [Phase 17]: [Phase 17-07]: AdminRolesView uses 300ms debounced per-role PUT with optimistic UI and server-truth revert on error; publication.create filtered out of matrix via PER_USER_ONLY_ACTIONS (per-user only, handled in 17-08)
- [Phase 17-permission-system-override]: Plan 17-08: «Доступ» section uses allOrgEntries (not rebuilt orgAccessList) and editDialog.userId (actual shape) per PLAN's adaptation clause
- [Phase 17-permission-system-override]: Plan 17-09: EMPLOYEE_ALLOWED removed outright (no fallback) — authStore.loaded fail-opens on API failure (17-06) + 17-01 seed grants employee defaults; double-gating would regress
- [Phase 17-permission-system-override]: Plan 17-09: Sub-routes share parent tab_key (/hierarchy→staff, /suppliers→contractors, /orders/*→purchases, service-notes/advance-reports sub-paths) — matches RESEARCH Open-Question 2
- [Phase 17-permission-system-override]: Plan 17-09: E2E uses inline loginAs(page,user,pwd) helper — existing helpers.ts login() is hardcoded to admin/admin123; keeps plan scope to two declared files

## Blockers

_нет активных блокеров_

### Closed 2026-04-19

- **INTERNAL_ERROR на /dashboard/radar** → оказалось не backend N+1, а frontend: ApexCharts получал negative `<circle r>` из unclamped `feoImbalance` score + `mode="out-in"` в `<transition>` не давал новой view монтироваться. Закрыто в `e9efc8d` + `c313c57`. Детали в 05_Gotchas.
- **PydanticSerializationError для WishItem** на `/api/wishes/` → `WishOut.items` был нетипизированным `list`. Pydantic не знал схему. Закрыто в `5c592d8` (items: List[WishItemOut]).
- **Автодеплой висел 2 дня** → webhook.py однопоточный HTTPServer в silent-hang. Закрыто в `2d04e4e` (ThreadingHTTPServer + always-restart + /healthz).
- **4 UX-бага Любарца на /my-tasks** → Phase 11 incomplete. Закрыто в `ce90039` (backend: employee + PurchaseMember + ?org_id) и `f3cf2cc` (frontend: org picker, flash, counter).

## Roadmap Evolution

- Phase 13 added: Заявки v3 — авторасспределение позиций по закупкам, drag-drop, автосоздание N закупок, служебная записка
- Phase 14 added: Risk Radar — альтернативный визуал Dashboard (Neon Telemetry стиль) с toggle classic/radar, без модификации DashboardView.vue
- Phase 16 added (2026-04-19): Refactor Monoliths — декомпозиция purchases.py (3200), tasks.py (1639), MyTasksView.vue (2155) в тематические модули ≤800 строк по принципу «один процесс — один модуль». Директория `.planning/phases/16-refactor-monoliths/`.
- Phase 17 added (2026-04-21): Permission System — конфигурируемая матрица ролей + индивидуальные override'ы (галочки в карточке пользователя → роль `Индивидуально`). Триггер: Любарец видит «Персонал» но редактировать не может. Директория TBD.
- Phase 18 added (2026-04-21): Staff Directory — read-only справочник коллег (ФИО, должность, телефон, email) фильтрованный по своим организациям, отдельно от админской вкладки «Персонал». Директория TBD.

## Pending from Feedback

- Drag & Drop для закрывающих документов
- Подсветка изменений (diff-tracking) в карточке задачи/закупки
- Автосохранение + Undo/Redo (Ctrl+Z/Y)
- Синхронизация договор ↔ закупка
- Бюджетная логика: Плановая vs ФЭО (пересмотр)
- Шаблоны слетают (лист согласования ФАДМ_26)
