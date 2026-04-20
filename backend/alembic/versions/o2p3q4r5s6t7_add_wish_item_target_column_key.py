"""add wish_items.target_column_key

Revision ID: o2p3q4r5s6t7
Revises: n1o2p3q4r5s6
Create Date: 2026-04-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'o2p3q4r5s6t7'
down_revision = 'n1o2p3q4r5s6'  # 13-01 migration — guaranteed present (Wave 2 runs after Wave 1)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('wish_items',
        sa.Column('target_column_key', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('wish_items', 'target_column_key')
