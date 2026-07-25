"""add commitment_quarter and planned_payment_month to purchases

Revision ID: n1o2p3q4r5s6
Revises: m7n8o9p0q1r2
Create Date: 2026-07-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'n1o2p3q4r5s6'
down_revision = 'm7n8o9p0q1r2'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c['name'] for c in insp.get_columns('purchases')}
    if 'commitment_quarter' not in cols:
        op.add_column('purchases', sa.Column('commitment_quarter', sa.SmallInteger(), nullable=True))
    if 'planned_payment_month' not in cols:
        op.add_column('purchases', sa.Column('planned_payment_month', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('purchases', 'planned_payment_month')
    op.drop_column('purchases', 'commitment_quarter')
