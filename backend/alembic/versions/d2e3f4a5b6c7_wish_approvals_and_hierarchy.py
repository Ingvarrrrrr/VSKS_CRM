"""wish_approvals table + hierarchy fields (department deputy/curator, user superior, wish approval_mode)

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-07-09 10:00:00.000000

Idempotent: table created only if absent (inspector-guarded); columns added only if
missing. Supports running upgrade head at startup without DDL conflicts.
"""
import sqlalchemy as sa
from alembic import op

revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def _cols(inspector, table):
    return {c['name'] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'wish_approvals' not in existing_tables:
        op.create_table(
            'wish_approvals',
            sa.Column('id', sa.Integer, primary_key=True, nullable=False),
            sa.Column('wish_id', sa.Integer,
                      sa.ForeignKey('wishes.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.Integer,
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('order_num', sa.Integer, nullable=False, server_default='0'),
            sa.Column('role_name', sa.String(255), nullable=True),
            sa.Column('approver_full_name', sa.String(500), nullable=True),
            sa.Column('is_auto', sa.Boolean, nullable=False, server_default='false'),
            sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
            sa.Column('comment', sa.Text, nullable=True),
            sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('decided_by_user_id', sa.Integer,
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=True),
        )
        op.create_index('ix_wish_approvals_wish_id', 'wish_approvals', ['wish_id'])
        op.create_index('ix_wish_approvals_user_id', 'wish_approvals', ['user_id'])

    if 'wishes' in existing_tables and 'approval_mode' not in _cols(inspector, 'wishes'):
        op.add_column('wishes', sa.Column('approval_mode', sa.String(20),
                      nullable=False, server_default='sequential'))

    if 'departments' in existing_tables:
        dcols = _cols(inspector, 'departments')
        if 'deputy_head_user_id' not in dcols:
            op.add_column('departments', sa.Column('deputy_head_user_id', sa.Integer,
                          sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True))
        if 'curator_user_id' not in dcols:
            op.add_column('departments', sa.Column('curator_user_id', sa.Integer,
                          sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True))

    if 'users' in existing_tables and 'superior_user_id' not in _cols(inspector, 'users'):
        op.add_column('users', sa.Column('superior_user_id', sa.Integer,
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'users' in existing_tables and 'superior_user_id' in _cols(inspector, 'users'):
        op.drop_column('users', 'superior_user_id')

    if 'departments' in existing_tables:
        dcols = _cols(inspector, 'departments')
        if 'curator_user_id' in dcols:
            op.drop_column('departments', 'curator_user_id')
        if 'deputy_head_user_id' in dcols:
            op.drop_column('departments', 'deputy_head_user_id')

    if 'wishes' in existing_tables and 'approval_mode' in _cols(inspector, 'wishes'):
        op.drop_column('wishes', 'approval_mode')

    if 'wish_approvals' in existing_tables:
        op.drop_table('wish_approvals')
