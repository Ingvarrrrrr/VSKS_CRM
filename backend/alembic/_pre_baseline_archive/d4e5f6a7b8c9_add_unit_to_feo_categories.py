"""add unit to feo_categories

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-04-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('feo_categories', sa.Column('unit', sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column('feo_categories', 'unit')
