"""add wish fields: category, priority, desired_date, link

Revision ID: g8h9i0j1k2l3
Revises: f7a8b9c0d1e2
Create Date: 2026-04-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g8h9i0j1k2l3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('wishes', sa.Column('category', sa.String(50), nullable=True))
    op.add_column('wishes', sa.Column('link', sa.String(2000), nullable=True))
    op.add_column('wishes', sa.Column('priority', sa.String(20), nullable=True))
    op.add_column('wishes', sa.Column('desired_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('wishes', 'desired_date')
    op.drop_column('wishes', 'priority')
    op.drop_column('wishes', 'link')
    op.drop_column('wishes', 'category')
