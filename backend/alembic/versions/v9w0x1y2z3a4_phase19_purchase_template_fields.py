"""phase19 purchase + subsidy template fields

Revision ID: v9w0x1y2z3a4
Revises: t7u8v9w0x1y2
Create Date: 2026-04-23

Phase 19.01 — adds purchase fields used by docx context templates
(submission deadline / delivery location / service term) and a large
agreement_text column on subsidies for the federal-budget / Росмолодёжь
clause.

Columns are nullable + idempotent (ADD COLUMN IF NOT EXISTS) so the
migration is safe to re-run.

Note: photo bytea migration (u8v9w0x1y2z3) is currently reverted in the
code branch; this revision chains directly on t7u8v9w0x1y2
(cascade_delete_platform_publications).
"""
from alembic import op
import sqlalchemy as sa

revision = 'v9w0x1y2z3a4'
down_revision = 't7u8v9w0x1y2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # ── purchases: Phase 19 template fields ───────────────────────────────
    connection.execute(sa.text("""
        ALTER TABLE purchases
          ADD COLUMN IF NOT EXISTS submission_deadline    TIMESTAMP      NULL,
          ADD COLUMN IF NOT EXISTS delivery_location      VARCHAR(500)   NULL,
          ADD COLUMN IF NOT EXISTS service_term_mode      VARCHAR(20)    NULL,
          ADD COLUMN IF NOT EXISTS service_term_days      INTEGER        NULL,
          ADD COLUMN IF NOT EXISTS service_term_type      VARCHAR(20)    NULL,
          ADD COLUMN IF NOT EXISTS service_deadline_date  DATE           NULL
    """))

    # service_start_date / service_end_date already exist on purchases
    # (added in Phase 1 contract-document generation fields) — re-use them.

    # ── subsidies: agreement_text block ───────────────────────────────────
    connection.execute(sa.text("""
        ALTER TABLE subsidies
          ADD COLUMN IF NOT EXISTS agreement_text TEXT NULL
    """))


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(sa.text("""
        ALTER TABLE subsidies
          DROP COLUMN IF EXISTS agreement_text
    """))

    connection.execute(sa.text("""
        ALTER TABLE purchases
          DROP COLUMN IF EXISTS submission_deadline,
          DROP COLUMN IF EXISTS delivery_location,
          DROP COLUMN IF EXISTS service_term_mode,
          DROP COLUMN IF EXISTS service_term_days,
          DROP COLUMN IF EXISTS service_term_type,
          DROP COLUMN IF EXISTS service_deadline_date
    """))
