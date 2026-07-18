"""add wish.source column

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = [c['name'] for c in inspector.get_columns('wishes')]
    if 'source' not in cols:
        op.add_column('wishes', sa.Column('source', sa.String(30), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = [c['name'] for c in inspector.get_columns('wishes')]
    if 'source' in cols:
        op.drop_column('wishes', 'source')
