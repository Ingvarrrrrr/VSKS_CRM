"""org_etp_keys_and_unified_terms

Revision ID: e5f7a9b1c3d5
Revises: d9a1b3c5e7f9
Create Date: 2026-11-21 14:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'e5f7a9b1c3d5'
down_revision = 'd9a1b3c5e7f9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if 'organizations' in tables:
        org_cols = {c['name'] for c in inspector.get_columns('organizations')}
        if 'roseltorg_token_encrypted' not in org_cols:
            op.execute(sa.text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS roseltorg_token_encrypted TEXT"))
        if 'fabrikant_login' not in org_cols:
            op.execute(sa.text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS fabrikant_login VARCHAR(255)"))
        if 'fabrikant_password_encrypted' not in org_cols:
            op.execute(sa.text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS fabrikant_password_encrypted TEXT"))

    if 'purchases' in tables:
        purch_cols = {c['name'] for c in inspector.get_columns('purchases')}
        if 'prepayment_percent' not in purch_cols:
            op.execute(sa.text("ALTER TABLE purchases ADD COLUMN IF NOT EXISTS prepayment_percent NUMERIC(5, 2)"))

        # Safe idempotent backfill for unified delivery term and address
        # 1. Срок поставки: если заполнен execution_term -> deadline; иначе если delivery_date -> deadline
        op.execute(sa.text("""
            UPDATE purchases
            SET service_term_mode = 'deadline',
                service_deadline_date = execution_term
            WHERE (service_term_mode IS NULL OR service_term_mode = '')
              AND execution_term IS NOT NULL;
        """))
        op.execute(sa.text("""
            UPDATE purchases
            SET service_term_mode = 'deadline',
                service_deadline_date = delivery_date,
                execution_term = delivery_date
            WHERE (service_term_mode IS NULL OR service_term_mode = '')
              AND delivery_date IS NOT NULL;
        """))

        # 2. Адрес поставки: старый скрытый delivery_address переносим в delivery_location
        op.execute(sa.text("""
            UPDATE purchases
            SET delivery_location = delivery_address,
                delivery_location_kind = COALESCE(delivery_location_kind, 'delivery')
            WHERE (delivery_location IS NULL OR delivery_location = '')
              AND delivery_address IS NOT NULL AND delivery_address <> '';
        """))


def downgrade() -> None:
    pass
