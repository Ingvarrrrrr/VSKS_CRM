"""user_subsidy_access — пер-пользовательский доступ к субсидиям

Revision ID: f5a6b7c8d9e0
Revises: e3f4a5b6c7d8
Create Date: 2026-06-24 12:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'f5a6b7c8d9e0'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_subsidy_access',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('subsidy_id', sa.Integer(), sa.ForeignKey('subsidies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=True, server_default='employee'),
        sa.UniqueConstraint('user_id', 'subsidy_id', name='uq_user_subsidy'),
    )


def downgrade() -> None:
    op.drop_table('user_subsidy_access')
