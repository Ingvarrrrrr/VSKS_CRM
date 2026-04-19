---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 13
status: Phase 15 complete — ready for Phase 13
last_updated: "2026-04-19T16:30:00.000Z"
progress:
  total_phases: 15
  completed_phases: 7
  total_plans: 35
  completed_plans: 30
---

# STATE.md — VSKS_CRM

## Current Position

Phase 15 (Reusable Purchase Items Editor) — ✅ COMPLETE (5/5 plans)
Next: Phase 13 (Заявки v3 — авторасспределение) — unblocked by Phase 15 shared editor

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

## Blockers

- **INTERNAL_ERROR на /dashboard/radar** (2026-04-19): диалог "Внутренняя ошибка сервера", ID 8af65587-5d12-4410-8538-55b914a89b5a. Traceback обрезан: видно `anyio.WouldBlock → anyio.EndOfStream` в starlette middleware base.py. Подозрение — N+1 SUM в `/api/contracts` (300+ контрактов × 3 SUM = 900 DB hits) × 4 параллельных запроса из `useRiskScores.refresh()` → exhaust DB pool. Ждём полный traceback от пользователя для точной диагностики.

## Roadmap Evolution

- Phase 13 added: Заявки v3 — авторасспределение позиций по закупкам, drag-drop, автосоздание N закупок, служебная записка
- Phase 14 added: Risk Radar — альтернативный визуал Dashboard (Neon Telemetry стиль) с toggle classic/radar, без модификации DashboardView.vue

## Pending from Feedback

- Drag & Drop для закрывающих документов
- Подсветка изменений (diff-tracking) в карточке задачи/закупки
- Автосохранение + Undo/Redo (Ctrl+Z/Y)
- Синхронизация договор ↔ закупка
- Бюджетная логика: Плановая vs ФЭО (пересмотр)
- Шаблоны слетают (лист согласования ФАДМ_26)
