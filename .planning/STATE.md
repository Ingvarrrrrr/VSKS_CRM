# STATE.md — VSKS_CRM

## Current State

- **Phase:** 0 (Pre-development)
- **Status:** Planning complete
- **Last Updated:** 2026-03-03

## Completed Phases

(none)

## Active Phase

None — run `/gsd:execute-phase 1` to begin

## Blockers

(none)

## Notes

- Existing codebase: auth, CRUD, dashboard, SubsidiesView all working
- Real data loaded: 390 purchases (ФАДМ_2026), 612 contractors
- DB tables already exist: `purchase_files`, `budget_history`, `wishes` (need to connect)
- All 390 ФАДМ_2026 purchases have `subsidy_id=7`, `feo_category_id=NULL`; total 36,810,006 ₽ vs subsidy limit 15,500,000 ₽ — historical overage, must not be blocked retroactively
- Tech stack locked: Vue 3 + FastAPI + PostgreSQL — no changes planned
- Files stored as PostgreSQL `bytea` (confirmed by client, no S3/MinIO needed)
- Status workflow is unidirectional; admin-only reverse is a Phase 1 decision already approved
- n8n is running but notifications are deferred to v2
