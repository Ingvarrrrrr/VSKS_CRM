"""users.can_merge_purchases — разрешение на объединение закупок

Пользователь с этим флагом (а также superadmin и account_owner по умолчанию)
может объединять несколько закупок в одну.

Revision ID: f7b8c9d0e1f2
Revises: e5f6g7h8i9j0
Create Date: 2026-11-03 16:50:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'f7b8c9d0e1f2'
down_revision = 'e5f6g7h8i9j0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'users' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('users')}
    if 'can_merge_purchases' not in cols:
        op.execute(sa.text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS can_merge_purchases "
            "BOOLEAN NOT NULL DEFAULT false"
        ))


def downgrade() -> None:
    pass
