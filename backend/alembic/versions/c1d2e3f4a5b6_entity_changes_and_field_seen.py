"""entity_changes and entity_field_seen tables

Revision ID: c1d2e3f4a5b6
Revises: b6c7d8e9f0a1
Create Date: 2026-07-06 12:00:00.000000

Idempotent: tables are only created if they do not yet exist (inspector-guarded).
Supports running upgrade head at startup without DDL conflicts if check_schema
already created the tables via SQLAlchemy create_all.
"""
import sqlalchemy as sa
from alembic import op

revision = 'c1d2e3f4a5b6'
down_revision = 'b6c7d8e9f0a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'entity_changes' not in existing_tables:
        op.create_table(
            'entity_changes',
            sa.Column('id', sa.Integer, primary_key=True, nullable=False),
            sa.Column('entity_type', sa.String(20), nullable=False),
            sa.Column('entity_id', sa.Integer, nullable=False),
            sa.Column('field_name', sa.String(64), nullable=False),
            sa.Column('old_value', sa.Text, nullable=True),
            sa.Column('new_value', sa.Text, nullable=True),
            sa.Column('changed_by_id', sa.Integer,
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('changed_by_name', sa.String(200), nullable=True),
            sa.Column('changed_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_entity_changes_entity_type', 'entity_changes', ['entity_type'])
        op.create_index('ix_entity_changes_entity_id', 'entity_changes', ['entity_id'])
        op.create_index('ix_entity_changes_changed_at', 'entity_changes', ['changed_at'])
        op.create_index('ix_entity_changes_type_id_at', 'entity_changes',
                        ['entity_type', 'entity_id', 'changed_at'])

    if 'entity_field_seen' not in existing_tables:
        op.create_table(
            'entity_field_seen',
            sa.Column('id', sa.Integer, primary_key=True, nullable=False),
            sa.Column('user_id', sa.Integer,
                      sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('entity_type', sa.String(20), nullable=False),
            sa.Column('entity_id', sa.Integer, nullable=False),
            sa.Column('field_name', sa.String(64), nullable=False),
            sa.Column('dismissed_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint('user_id', 'entity_type', 'entity_id', 'field_name',
                                name='uq_entity_field_seen'),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'entity_field_seen' in existing_tables:
        op.drop_table('entity_field_seen')

    if 'entity_changes' in existing_tables:
        op.drop_table('entity_changes')
