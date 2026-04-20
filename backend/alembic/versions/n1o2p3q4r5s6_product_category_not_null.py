"""product category NOT NULL with backfill

Revision ID: n1o2p3q4r5s6
Revises: h1i2j3k4l5m6
Create Date: 2026-04-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'n1o2p3q4r5s6'
down_revision = 'h1i2j3k4l5m6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: backfill NULL rows with 'Прочее' (per CONTEXT D-03)
    op.execute("UPDATE products SET category = 'Прочее' WHERE category IS NULL")
    # Step 2: flip column to NOT NULL
    op.alter_column(
        'products', 'category',
        existing_type=sa.String(length=200),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'products', 'category',
        existing_type=sa.String(length=200),
        nullable=True,
    )
    # Do NOT revert 'Прочее' backfill — cannot distinguish original NULLs from user-entered 'Прочее'
