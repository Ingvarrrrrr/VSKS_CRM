"""add planned_amount to feo_categories

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'feo_categories',
        sa.Column('planned_amount', sa.Numeric(15, 2), nullable=True)
    )


def downgrade():
    op.drop_column('feo_categories', 'planned_amount')
