---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Ready to execute
last_updated: "2026-04-20T12:44:11.826Z"
progress:
  total_phases: 16
  completed_phases: 8
  total_plans: 57
  completed_plans: 47
---

# STATE.md — VSKS_CRM

## Current Position

Phase: 13 (v3-drag-drop-n) — EXECUTING
Plan: 2 of 7
Phase 16 (Refactor Monoliths) — 📝 CONTEXT.md captured (2026-04-19), 0 plans yet
Next action: `/gsd:plan-phase 16` (will create PLAN.md files from CONTEXT decisions)

Recent (parked): Phase 13 (Заявки v3 — авторасспределение) — unblocked by Phase 15, waiting after Phase 16.

- **Milestone:** v1.0
- **Last Completed Phase:** 15
- **Previous Phase:** 14.1 (Risk Radar — nav + formulas dialog)
- **Profile:** balanced (Opus plans, Sonnet executes)

## Status

- Phases 1-9, 11, 14, 15: ✅ Complete
- Phase 10: 🟡 3/4 plans done (1 remaining: AppBar chat integration)
- Phase 12: 📋 4 plans ready, 0 executed
- Phase 13: 📋 ready to plan (Phase 15 unblocks it)
- Post-phase feedback work: ✅ Delivered (Голичков-3, Суперадмин-1, Суперадмин-2, Суперадмин-3)

## Recent Activity (April 2026)

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

## Pending from Feedback

- Drag & Drop для закрывающих документов
- Подсветка изменений (diff-tracking) в карточке задачи/закупки
- Автосохранение + Undo/Redo (Ctrl+Z/Y)
- Синхронизация договор ↔ закупка
- Бюджетная логика: Плановая vs ФЭО (пересмотр)
- Шаблоны слетают (лист согласования ФАДМ_26)
