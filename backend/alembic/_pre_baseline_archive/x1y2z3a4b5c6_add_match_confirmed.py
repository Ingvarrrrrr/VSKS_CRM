"""phase21 add match_confirmed flag to purchase_items

Revision ID: x1y2z3a4b5c6
Revises: w0x1y2z3a4b5
Create Date: 2026-04-26

Phase 21.06 — receipt JSON import auto-matches items to catalog products by
name. Each auto-matched item must be explicitly confirmed by the user before
the advance report can be saved. This column tracks per-item confirmation
state. All pre-existing items are considered confirmed (default TRUE).
"""
from alembic import op
import sqlalchemy as sa


revision = 'x1y2z3a4b5c6'
down_revision = 'w0x1y2z3a4b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE purchase_items "
        "ADD COLUMN IF NOT EXISTS match_confirmed BOOLEAN NOT NULL DEFAULT TRUE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE purchase_items DROP COLUMN IF EXISTS match_confirmed")
