"""feo_categories: add description and feo_amount columns

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-07-22 00:00:00.000000
"""
from alembic import op
from sqlalchemy import text


revision = 'l6m7n8o9p0q1'
down_revision = 'k5l6m7n8o9p0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Идемпотентно добавляем колонки
    op.execute(text(
        "ALTER TABLE feo_categories ADD COLUMN IF NOT EXISTS description TEXT"
    ))
    op.execute(text(
        "ALTER TABLE feo_categories ADD COLUMN IF NOT EXISTS feo_amount NUMERIC(15,2)"
    ))


def downgrade() -> None:
    op.execute(text("ALTER TABLE feo_categories DROP COLUMN IF EXISTS description"))
    op.execute(text("ALTER TABLE feo_categories DROP COLUMN IF EXISTS feo_amount"))
