"""user_subsidy_permission_overrides — пер-субсидия оверрайды листов/действий

Revision ID: b2c3d4e5f6a7
Revises: f5a6b7c8d9e0
Create Date: 2026-06-25 12:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'b2c3d4e5f6a7'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if 'user_subsidy_permission_overrides' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'user_subsidy_permission_overrides',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_subsidy_access_id', sa.Integer(), sa.ForeignKey('user_subsidy_access.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('granted', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('user_subsidy_access_id', 'key', name='uq_usa_override'),
    )


def downgrade() -> None:
    op.drop_table('user_subsidy_permission_overrides')
