"""Add customer_id and calculated_budget to subsidies

Revision ID: add_customer_calc_budget
Revises: bcbeb8647a09_add_subsidy_and_appendix
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_customer_calc_budget'
down_revision = 'bcbeb8647a09_add_subsidy_and_appendix'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('subsidies', sa.Column('calculated_budget', sa.Float(), nullable=True))
    op.add_column('subsidies', sa.Column('customer_id', sa.Integer(), sa.ForeignKey('contractors.id'), nullable=True))

def downgrade() -> None:
    op.drop_column('subsidies', 'customer_id')
    op.drop_column('subsidies', 'calculated_budget')
