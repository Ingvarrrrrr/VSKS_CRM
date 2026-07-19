"""add feo planned dates and needed dates

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    # feo_planned_items: payment_mode, planned_date, monthly_start_date, months_count, monthly_amount
    cols = [c['name'] for c in inspector.get_columns('feo_planned_items')]
    if 'payment_mode' not in cols:
        op.add_column('feo_planned_items', sa.Column('payment_mode', sa.String(20), nullable=False, server_default='one_time'))
    if 'planned_date' not in cols:
        op.add_column('feo_planned_items', sa.Column('planned_date', sa.Date(), nullable=True))
    if 'monthly_start_date' not in cols:
        op.add_column('feo_planned_items', sa.Column('monthly_start_date', sa.Date(), nullable=True))
    if 'months_count' not in cols:
        op.add_column('feo_planned_items', sa.Column('months_count', sa.Integer(), nullable=True))
    if 'monthly_amount' not in cols:
        op.add_column('feo_planned_items', sa.Column('monthly_amount', sa.Numeric(15, 2), nullable=True))

    # wish_items: needed_date
    cols = [c['name'] for c in inspector.get_columns('wish_items')]
    if 'needed_date' not in cols:
        op.add_column('wish_items', sa.Column('needed_date', sa.Date(), nullable=True))

    # purchase_items: needed_date
    cols = [c['name'] for c in inspector.get_columns('purchase_items')]
    if 'needed_date' not in cols:
        op.add_column('purchase_items', sa.Column('needed_date', sa.Date(), nullable=True))

    # subsidies: require_planned_dates
    cols = [c['name'] for c in inspector.get_columns('subsidies')]
    if 'require_planned_dates' not in cols:
        op.add_column('subsidies', sa.Column('require_planned_dates', sa.Boolean(), nullable=False, server_default='true'))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    # subsidies
    cols = [c['name'] for c in inspector.get_columns('subsidies')]
    if 'require_planned_dates' in cols:
        op.drop_column('subsidies', 'require_planned_dates')

    # purchase_items
    cols = [c['name'] for c in inspector.get_columns('purchase_items')]
    if 'needed_date' in cols:
        op.drop_column('purchase_items', 'needed_date')

    # wish_items
    cols = [c['name'] for c in inspector.get_columns('wish_items')]
    if 'needed_date' in cols:
        op.drop_column('wish_items', 'needed_date')

    # feo_planned_items
    cols = [c['name'] for c in inspector.get_columns('feo_planned_items')]
    if 'monthly_amount' in cols:
        op.drop_column('feo_planned_items', 'monthly_amount')
    if 'months_count' in cols:
        op.drop_column('feo_planned_items', 'months_count')
    if 'monthly_start_date' in cols:
        op.drop_column('feo_planned_items', 'monthly_start_date')
    if 'planned_date' in cols:
        op.drop_column('feo_planned_items', 'planned_date')
    if 'payment_mode' in cols:
        op.drop_column('feo_planned_items', 'payment_mode')
