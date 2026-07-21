"""fabrikant: per-user platform creds + new fields (agreement_number, contract_city, payment_term_days, applications_review_date)

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-07-21 00:00:00.000000
"""
from alembic import op
from sqlalchemy import text


revision = 'i3j4k5l6m7n8'
down_revision = 'h2i3j4k5l6m7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. user_platform_credentials — create if not exists
    has_table = conn.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_name='user_platform_credentials')"
    )).scalar()
    if not has_table:
        op.execute(text("""
            CREATE TABLE user_platform_credentials (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                platform VARCHAR(50) NOT NULL,
                login VARCHAR(255) NOT NULL,
                encrypted_password TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_user_platform_credential UNIQUE (user_id, platform)
            )
        """))
        op.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_user_platform_credentials_user_id "
            "ON user_platform_credentials (user_id)"
        ))

    # 2. subsidies.agreement_number
    op.execute(text(
        "ALTER TABLE subsidies ADD COLUMN IF NOT EXISTS agreement_number VARCHAR(200)"
    ))

    # 3. organizations.contract_city
    op.execute(text(
        "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS contract_city VARCHAR(200)"
    ))

    # 4. purchases.payment_term_days
    op.execute(text(
        "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS payment_term_days INTEGER"
    ))

    # 5. purchases.applications_review_date
    op.execute(text(
        "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS applications_review_date DATE"
    ))


def downgrade() -> None:
    op.execute(text("ALTER TABLE purchases DROP COLUMN IF EXISTS applications_review_date"))
    op.execute(text("ALTER TABLE purchases DROP COLUMN IF EXISTS payment_term_days"))
    op.execute(text("ALTER TABLE organizations DROP COLUMN IF EXISTS contract_city"))
    op.execute(text("ALTER TABLE subsidies DROP COLUMN IF EXISTS agreement_number"))
    op.execute(text("DROP TABLE IF EXISTS user_platform_credentials"))
