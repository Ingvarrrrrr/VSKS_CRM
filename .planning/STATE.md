# STATE.md — VSKS_CRM

## Current State

- **Phase:** 8 (Торговые площадки + КП email + E2E)
- **Current Plan:** 08-04 (completed)
- **Status:** Phase 08 complete
- **Last Updated:** 2026-03-20 (08-04 completed)

## Completed Phases

- Phase 1: Purchase Form + Status Workflow — ✓ completed outside GSD (before tracking started)
- Phase 2: Cascading FEO + Budget Validation — ✓ completed outside GSD
- Phase 3: File Attachments — ✓ completed outside GSD
- Phase 4: Contract Registry — ✓ completed outside GSD
- Phase 5: Export / Import Excel — ✓ completed outside GSD

## Completed Phases (additional)

- Phase 8: Торговые площадки + КП email + E2E — ✓ completed 2026-03-20
  - roseltorg_publish.json (n8n, production URL + token check + procedure_type mapping) — активен на сервере
  - fabrikant_publish.json (test mode FABRIKANT_TEST_MODE=true) — активен на сервере
  - CreateOrderView.vue — двухшаговый диалог с dropdown для Росэлторг
  - E2E тесты (e2e/12-publications.spec.ts) — 4 теста, все pass
  - n8n на сервере: ROSELTORG_TOKEN, FABRIKANT_TEST_MODE=true в env
  - n8n пароль admin: Admin123! (был reset)

## Active Phase

Phase 6: Analytics + Budget History — partially implemented (dashboard KPIs + charts exist; budget history log needs verification; FEO drill-down in BudgetDrillDownDialog needs check)

## Additional Work Identified (not in original roadmap)

- **Multi-tenancy org-isolation audit** — `org_id` filter missing or unverified in: `contracts.py`, `feo_categories.py`, `dashboard.py`, `payments.py`, `commercial_requests.py`, `publications.py`, `subsidy_approvers.py`, `responsible_persons.py`
- **SMTP email verification** — backend ready (dev mode logs link); needs Yandex 360 app password to configure in docker-compose.yml
- **Bug: access_token vs auth_token** — file-upload code reads `access_token` from localStorage but api.ts stores `auth_token` → uploads fail silently
- **Dead code cleanup** — AddProductDialog×3, ProductSelector×3, DashboardViewSimple, CreateOrderViewSimple, CreateOrderView.backup
- **Landing page + dark theme** — ✓ completed (LandingView.vue, vuetify.ts dark theme, router guards)
- **Multi-tenancy frontend** — ✓ completed (RegisterView, VerifyEmailView, OrganizationsView, AppBar updates)

## Accumulated Context

### Roadmap Evolution
- Phase 8 added: Торговые площадки + КП email + E2E (n8n Росэлторг, Фабрикант test mode, SMTP КП, Playwright)

## Blockers

- ~~SMTP~~ ✅ настроен (szbgaktpqomcwdou)
- Фабрикант: IP whitelist от поддержки (403)

## Key Decisions

- Multi-tenancy: org_id on all entities, superadmin sees all, org_admin/manager/employee see own org only
- Files stored as PostgreSQL bytea (no S3/MinIO)
- n8n notifications deferred to v2
- Status workflow is unidirectional; admin-only reverse approved
- Tech stack locked: Vue 3 + FastAPI + PostgreSQL
- [08-01] procedure_type оставлен Optional[str] без enum-валидации — значения templateId уточнятся после токена Росэлторг
- [08-01] Обогащение n8n payload в publish_purchase (не в _build_publish_payload) — сохраняет чистоту helper-функции
- [08-02] ROSELTORG_TOKEN env var in n8n — empty token causes error callback with descriptive message (не падает молча)
- [08-02] FABRIKANT_TEST_MODE проверяется как строка === 'true' для совместимости с n8n Variables
- [08-03] Росэлторг publish uses two-step dialog with mandatory procedure_type dropdown; procedure_type sent to API in request body
- [08-04] 409 on duplicate publication handled gracefully — GET existing pub list as fallback; nginx 307 redirect drops auth header — use trailing slash URLs; create-order route is /orders/{id}/edit

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | Улучшить визуализацию FruitShop магазина | 2026-03-27 | 199a137 | [1-fruitshop](./quick/1-fruitshop/) |

## Notes

- Real data: 390 purchases (ФАДМ_2026, subsidy_id=7), 612 contractors
- All 390 ФАДМ_2026 purchases have feo_category_id=NULL; total 36.8M₽ vs limit 15.5M₽ — historical overage, must not be blocked retroactively
- subsidy_id=7 (ФАДМ_2026) requires ?admin_override=true for new purchases
- Docker: NO volume mount for code → any change requires image rebuild
