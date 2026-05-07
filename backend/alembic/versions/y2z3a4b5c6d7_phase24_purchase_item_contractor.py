"""phase24 per-item contractor columns on purchase_items

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2026-05-04

Phase 24 — each purchase item can carry its own contractor reference
(auto-populated from FNS receipt seller ИНН). Three new columns:
  contractor_id   FK → contractors(id) SET NULL on delete
  contractor_inn  raw ИНН string (denormalised for display without join)
  contractor_name raw name string (ditto)
"""
from alembic import op
import sqlalchemy as sa


revision = 'y2z3a4b5c6d7'
down_revision = 'x1y2z3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE purchase_items "
        "ADD COLUMN IF NOT EXISTS contractor_id INTEGER "
        "REFERENCES contractors(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE purchase_items "
        "ADD COLUMN IF NOT EXISTS contractor_inn VARCHAR(20)"
    )
    op.execute(
        "ALTER TABLE purchase_items "
        "ADD COLUMN IF NOT EXISTS contractor_name VARCHAR(500)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE purchase_items DROP COLUMN IF EXISTS contractor_name")
    op.execute("ALTER TABLE purchase_items DROP COLUMN IF EXISTS contractor_inn")
    op.execute("ALTER TABLE purchase_items DROP COLUMN IF EXISTS contractor_id")
