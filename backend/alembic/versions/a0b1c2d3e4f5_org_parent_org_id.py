"""org hierarchy: organizations.parent_org_id (вышестоящая орг для оргчарта)

Отдельное поле подчинения орг→орг для редактора иерархии. НЕ путать с
root_org_id (контур аккаунта, влияет на видимость) — parent_org_id это чистая
оргструктура «кто кому подчиняется», рисуется стрелками и не наследует видимость.

Idempotent: ADD COLUMN IF NOT EXISTS с self-FK ON DELETE SET NULL под guard.

Revision ID: a0b1c2d3e4f5
Revises: e4f5a6b7c8d9
Create Date: 2026-07-09 14:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'a0b1c2d3e4f5'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'organizations' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('organizations')}
    if 'parent_org_id' not in cols:
        op.execute(sa.text(
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS parent_org_id INTEGER "
            "REFERENCES organizations(id) ON DELETE SET NULL"
        ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE organizations DROP COLUMN IF EXISTS parent_org_id"))
