"""add platform_number and platform_state to platform_publications

Revision ID: q4r5s6t7u8v9
Revises: p3q4r5s6t7u8
Create Date: 2026-07-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'q4r5s6t7u8v9'
down_revision = 'p3q4r5s6t7u8'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    existing_tables = set(insp.get_table_names())
    if 'platform_publications' not in existing_tables:
        return

    existing_cols = {c['name'] for c in insp.get_columns('platform_publications')}

    if 'platform_number' not in existing_cols:
        op.add_column(
            'platform_publications',
            sa.Column('platform_number', sa.String(50), nullable=True),
        )

    if 'platform_state' not in existing_cols:
        op.add_column(
            'platform_publications',
            sa.Column('platform_state', sa.String(100), nullable=True),
        )


def downgrade():
    op.drop_column('platform_publications', 'platform_state')
    op.drop_column('platform_publications', 'platform_number')
