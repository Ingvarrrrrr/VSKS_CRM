# STATE.md — VSKS_CRM

## Current State

- **Phase:** 6 (Analytics + Budget History)
- **Status:** In progress
- **Last Updated:** 2026-03-14

## Completed Phases

- Phase 1: Purchase Form + Status Workflow — ✓ completed outside GSD (before tracking started)
- Phase 2: Cascading FEO + Budget Validation — ✓ completed outside GSD
- Phase 3: File Attachments — ✓ completed outside GSD
- Phase 4: Contract Registry — ✓ completed outside GSD
- Phase 5: Export / Import Excel — ✓ completed outside GSD

## Active Phase

Phase 6: Analytics + Budget History — partially implemented (dashboard KPIs + charts exist; budget history log needs verification; FEO drill-down in BudgetDrillDownDialog needs check)

## Additional Work Identified (not in original roadmap)

- **Multi-tenancy org-isolation audit** — `org_id` filter missing or unverified in: `contracts.py`, `feo_categories.py`, `dashboard.py`, `payments.py`, `commercial_requests.py`, `publications.py`, `subsidy_approvers.py`, `responsible_persons.py`
- **SMTP email verification** — backend ready (dev mode logs link); needs Yandex 360 app password to configure in docker-compose.yml
- **Bug: access_token vs auth_token** — file-upload code reads `access_token` from localStorage but api.ts stores `auth_token` → uploads fail silently
- **Dead code cleanup** — AddProductDialog×3, ProductSelector×3, DashboardViewSimple, CreateOrderViewSimple, CreateOrderView.backup
- **Landing page + dark theme** — ✓ completed (LandingView.vue, vuetify.ts dark theme, router guards)
- **Multi-tenancy frontend** — ✓ completed (RegisterView, VerifyEmailView, OrganizationsView, AppBar updates)

## Blockers

- SMTP app password not yet obtained for z@vsks.ru (Yandex 360)

## Key Decisions

- Multi-tenancy: org_id on all entities, superadmin sees all, org_admin/manager/employee see own org only
- Files stored as PostgreSQL bytea (no S3/MinIO)
- n8n notifications deferred to v2
- Status workflow is unidirectional; admin-only reverse approved
- Tech stack locked: Vue 3 + FastAPI + PostgreSQL

## Notes

- Real data: 390 purchases (ФАДМ_2026, subsidy_id=7), 612 contractors
- All 390 ФАДМ_2026 purchases have feo_category_id=NULL; total 36.8M₽ vs limit 15.5M₽ — historical overage, must not be blocked retroactively
- subsidy_id=7 (ФАДМ_2026) requires ?admin_override=true for new purchases
- Docker: NO volume mount for code → any change requires image rebuild
