---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 15
status: Ready to execute
last_updated: "2026-04-19T12:34:58.942Z"
progress:
  total_phases: 15
  completed_phases: 6
  total_plans: 35
  completed_plans: 28
---

# STATE.md — VSKS_CRM

## Current Position

Phase: 15 (Reusable Purchase Items Editor) — EXECUTING
Plan: 4 of 5

- **Milestone:** v1.0
- **Current Phase:** 15
- **Previous Phase:** 10 (Chat Telegram UI) — 3/4 plans executed, 1 remaining
- **Profile:** balanced (Opus plans, Sonnet executes)

## Status

- Phases 1-9, 11: ✅ Complete
- Phase 10: 🟡 3/4 plans done (1 remaining: AppBar chat integration)
- Phase 12: 📋 4 plans ready, 0 executed
- Post-phase feedback work: ✅ Delivered (Голичков-3, Суперадмин-1, Суперадмин-2)

## Recent Activity (April 2026)

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

## Blockers

- (none active)

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
