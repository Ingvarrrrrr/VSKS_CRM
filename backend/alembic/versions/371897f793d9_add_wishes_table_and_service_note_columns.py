"""add_wishes_table_and_service_note_columns

Revision ID: 371897f793d9
Revises: bcbeb8647a09
Create Date: 2026-04-05 20:24:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '371897f793d9'
down_revision: Union[str, None] = 'bcbeb8647a09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop FK from purchases to old wishes table (old schema)
    op.drop_constraint('purchases_wish_id_fkey', 'purchases', type_='foreignkey', if_exists=True)

    # Drop old wishes table (different schema, no data)
    op.drop_table('wishes', if_exists=True)

    # Create new wishes table with D-02 schema
    op.create_table(
        'wishes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('quantity', sa.Numeric(15, 4), nullable=True),
        sa.Column('unit', sa.String(50), nullable=True),
        sa.Column('estimated_price', sa.Numeric(15, 2), nullable=True),
        sa.Column('justification', sa.Text(), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='draft'),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('purchase_id', sa.Integer(), sa.ForeignKey('purchases.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_wishes_id', 'wishes', ['id'])
    op.create_index('ix_wishes_org_id', 'wishes', ['org_id'])
    op.create_index('ix_wishes_status', 'wishes', ['status'])

    # Add service_note columns to purchases
    op.add_column('purchases', sa.Column('service_note_text', sa.Text(), nullable=True))
    op.add_column('purchases', sa.Column('service_note_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('purchases', sa.Column('service_note_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('purchases', 'service_note_at')
    op.drop_column('purchases', 'service_note_by')
    op.drop_column('purchases', 'service_note_text')
    op.drop_index('ix_wishes_status', table_name='wishes')
    op.drop_index('ix_wishes_org_id', table_name='wishes')
    op.drop_index('ix_wishes_id', table_name='wishes')
    op.drop_table('wishes')
