"""phase25: report_configs table

Revision ID: phase25rc
Revises: None
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'phase25rc'
down_revision = None  # alembic chain сломан — таблица создаётся через check_schema / Base.metadata.create_all
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'report_configs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('org_id', sa.Integer, sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.String(1000), nullable=True),
        sa.Column('config_json', JSONB, nullable=False, server_default='{}'),
        sa.Column('parameters_json', JSONB, nullable=False, server_default='[]'),
        sa.Column('created_by_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('is_default', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('is_shared', sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint('org_id', 'name', 'kind', name='uq_report_configs_org_name_kind'),
        sa.Index('ix_report_configs_org_id', 'org_id'),
    )


def downgrade():
    op.drop_table('report_configs')
