"""contracts.price_shared — разрешение делиться договорными ценами по конкретному договору.

По умолчанию False (не делиться). Другие организации видят договорные цены
только если в договоре включён этот флаг. Своя организация видит всегда,
superadmin видит всё.

Revision ID: d9a1b3c5e7f9
Revises: c3e5f7a9b1d3
Create Date: 2026-11-21 13:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'd9a1b3c5e7f9'
down_revision = 'c3e5f7a9b1d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'contracts' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('contracts')}
    if 'price_shared' not in cols:
        op.execute(sa.text(
            "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS price_shared "
            "BOOLEAN NOT NULL DEFAULT false"
        ))


def downgrade() -> None:
    pass
