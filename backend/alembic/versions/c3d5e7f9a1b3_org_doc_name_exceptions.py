"""organizations.doc_name_exceptions — исключения регистра/написания для
подстановки полного наименования организации (из ЕГРЮЛ, обычно КАПСОМ) в
документы (владелец, 27.10.2026). Читается app/services/documents/
org_name_case.py::org_name_exceptions(); по одному слову/фразе в строке.

Idempotent: ADD COLUMN IF NOT EXISTS под inspector-guard, как соседние
миграции на organizations (a0b1c2d3e4f5, product_barcodes и т.п.).

Revision ID: c3d5e7f9a1b3
Revises: b8c0d2e4f6a8
Create Date: 2026-10-27 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'c3d5e7f9a1b3'
down_revision = 'b8c0d2e4f6a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'organizations' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('organizations')}
    if 'doc_name_exceptions' not in cols:
        op.execute(sa.text(
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS doc_name_exceptions TEXT"
        ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE organizations DROP COLUMN IF EXISTS doc_name_exceptions"))
