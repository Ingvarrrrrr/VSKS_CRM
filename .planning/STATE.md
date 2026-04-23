---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Ready to execute
last_updated: "2026-04-23T09:24:17.331Z"
progress:
  total_phases: 18
  completed_phases: 9
  total_plans: 66
  completed_plans: 55
---

# STATE.md — VSKS_CRM

## Current Position

Phase: 17 (permission-system-override) — EXECUTING
Plan: 3 of 9
Next action: `/gsd:plan-phase 17` — создать PLAN.md файлы из CONTEXT решений
Resume file: None

Recently closed:

- Phase 13 — Заявки v3 канбан + split purchase kanban (7/7 планов, commits 9ae0202, c2312f8, f40546c, d1b3cb9, fcbed67)
- Phase 16 — Refactor monoliths (15/15, 16-15-UAT pass)
- Phase 15 — PurchaseItemsEditor extraction (5/5)

- **Milestone:** v1.0
- **Last Completed Phase:** 16 → 13 (в порядке закрытия)
- **Profile:** balanced (Opus plans, Sonnet executes)

## Status

- ✅ Complete (13): Phases 1–9, 11, 13, 15, 16
- 🟡 In progress (2): Phase 10 (3/4 — осталось 10-04 AppBar chat nav+badge), Phase 14 (3/4 — осталось 14-04 polish+UAT)
- ⏳ Not started (3): Phase 12 (4 плана ready), Phase 17 Permission System (TBD), Phase 18 Staff Directory (TBD)
- Post-phase feedback work: ✅ Delivered (Голичков-3, Суперадмин-1, Суперадмин-2, Суперадмин-3)

## Recent Activity (April 2026)

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
