"""Add wish_members table for wish participant consent flow

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-06-05 20:00:00.000000

Зеркало purchase_members: участники заявки (wish) с consent-флоу.
ОДИН statement на create_table (asyncpg-safe), индекс отдельным op.create_index.
"""
import sqlalchemy as sa
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = 'f3a4b5c6d7e8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'wish_members' not in insp.get_table_names():
        op.create_table(
            'wish_members',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('wish_id', sa.Integer(),
                      sa.ForeignKey('wishes.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('user_id', sa.Integer(),
                      sa.ForeignKey('users.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('role', sa.String(50), server_default='participant', nullable=True),
            sa.Column('added_by_id', sa.Integer(),
                      sa.ForeignKey('users.id', ondelete='SET NULL'),
                      nullable=True),
            sa.Column('consent_pending', sa.Boolean(), server_default='false', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        )
        existing_idx = []
    else:
        existing_idx = [ix['name'] for ix in insp.get_indexes('wish_members')]
    if 'ix_wish_members_wish_id' not in existing_idx:
        op.create_index('ix_wish_members_wish_id', 'wish_members', ['wish_id'])


def downgrade() -> None:
    op.drop_table('wish_members')
