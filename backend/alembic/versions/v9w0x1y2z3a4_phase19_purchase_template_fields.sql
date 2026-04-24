-- Phase 19.01 — equivalent SQL for v9w0x1y2z3a4_phase19_purchase_template_fields.py
-- Chains on t7u8v9w0x1y2 (cascade_delete_platform_publications)
-- Idempotent: ADD COLUMN IF NOT EXISTS everywhere.
-- Run manually on prod if alembic upgrade is not possible.

-- ── purchases: Phase 19 template fields ───────────────────────────────
ALTER TABLE purchases
  ADD COLUMN IF NOT EXISTS submission_deadline    TIMESTAMP      NULL,
  ADD COLUMN IF NOT EXISTS delivery_location      VARCHAR(500)   NULL,
  ADD COLUMN IF NOT EXISTS service_term_mode      VARCHAR(20)    NULL,
  ADD COLUMN IF NOT EXISTS service_term_days      INTEGER        NULL,
  ADD COLUMN IF NOT EXISTS service_term_type      VARCHAR(20)    NULL,
  ADD COLUMN IF NOT EXISTS service_deadline_date  DATE           NULL;

-- ── subsidies: agreement_text block ───────────────────────────────────
ALTER TABLE subsidies
  ADD COLUMN IF NOT EXISTS agreement_text TEXT NULL;

-- Mark alembic revision so `alembic upgrade head` treats this as applied.
-- Uncomment the next line only if you're applying this SQL manually BEFORE
-- alembic catches up. Otherwise let alembic manage the version table itself.
-- UPDATE alembic_version SET version_num = 'v9w0x1y2z3a4';
