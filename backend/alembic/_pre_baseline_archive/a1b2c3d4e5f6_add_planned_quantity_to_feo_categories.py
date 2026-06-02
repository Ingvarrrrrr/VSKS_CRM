"""add_planned_quantity_to_feo_categories

Revision ID: a1b2c3d4e5f6
Revises: 2428adcca629, 371897f793d9
Create Date: 2026-04-05 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Union

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[tuple, None] = ('2428adcca629', '371897f793d9')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'feo_categories',
        sa.Column('planned_quantity', sa.Numeric(15, 2), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('feo_categories', 'planned_quantity')
