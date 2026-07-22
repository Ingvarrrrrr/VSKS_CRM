"""feo_categories: add feo_quantity and feo_unit columns

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-07-21 00:00:00.000000
"""
from alembic import op
from sqlalchemy import text


revision = 'k5l6m7n8o9p0'
down_revision = 'j4k5l6m7n8o9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Идемпотентно добавляем колонки
    op.execute(text(
        "ALTER TABLE feo_categories ADD COLUMN IF NOT EXISTS feo_quantity NUMERIC(15,2)"
    ))
    op.execute(text(
        "ALTER TABLE feo_categories ADD COLUMN IF NOT EXISTS feo_unit VARCHAR(50)"
    ))
    # Backfill: копируем существующие planned_quantity → feo_quantity, unit → feo_unit
    op.execute(text(
        """
        UPDATE feo_categories
        SET feo_quantity = planned_quantity,
            feo_unit = unit
        WHERE planned_quantity IS NOT NULL
          AND feo_quantity IS NULL
        """
    ))


def downgrade() -> None:
    op.execute(text("ALTER TABLE feo_categories DROP COLUMN IF EXISTS feo_quantity"))
    op.execute(text("ALTER TABLE feo_categories DROP COLUMN IF EXISTS feo_unit"))
