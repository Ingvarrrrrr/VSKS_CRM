"""add_parent_purchase_id_for_split

Revision ID: p3q4r5s6t7u8
Revises: o2p3q4r5s6t7
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'p3q4r5s6t7u8'
down_revision = 'o2p3q4r5s6t7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('purchases', sa.Column('parent_purchase_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_purchases_parent_purchase_id',
        'purchases', 'purchases',
        ['parent_purchase_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint('fk_purchases_parent_purchase_id', 'purchases', type_='foreignkey')
    op.drop_column('purchases', 'parent_purchase_id')
