"""add wish_items table and wish fields (subsidy_id, feo_category_id, assigned_to)

Revision ID: h1i2j3k4l5m6
Revises: g8h9i0j1k2l3
Create Date: 2026-04-14 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'h1i2j3k4l5m6'
down_revision = 'g8h9i0j1k2l3'
branch_labels = None
depends_on = None


def upgrade():
    # New columns on wishes
    op.add_column('wishes', sa.Column('subsidy_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_wishes_subsidy_id', 'wishes', 'subsidies',
        ['subsidy_id'], ['id'], ondelete='SET NULL'
    )
    op.add_column('wishes', sa.Column('feo_category_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_wishes_feo_category_id', 'wishes', 'feo_categories',
        ['feo_category_id'], ['id'], ondelete='SET NULL'
    )
    op.add_column('wishes', sa.Column('assigned_to', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_wishes_assigned_to', 'wishes', 'users',
        ['assigned_to'], ['id'], ondelete='SET NULL'
    )

    # New table wish_items
    op.create_table(
        'wish_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('wish_id', sa.Integer(), sa.ForeignKey('wishes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='SET NULL'), nullable=True),
        sa.Column('item_name', sa.Text(), nullable=False),
        sa.Column('item_type', sa.String(20), server_default='товар'),
        sa.Column('quantity', sa.Numeric(15, 4), server_default='1'),
        sa.Column('unit', sa.String(50), server_default='шт'),
        sa.Column('unit_price', sa.Numeric(15, 2), server_default='0'),
        sa.Column('total_price', sa.Numeric(15, 2), server_default='0'),
        sa.Column('country_origin', sa.String(100), server_default='Россия'),
    )


def downgrade():
    op.drop_table('wish_items')
    op.drop_constraint('fk_wishes_assigned_to', 'wishes', type_='foreignkey')
    op.drop_column('wishes', 'assigned_to')
    op.drop_constraint('fk_wishes_feo_category_id', 'wishes', type_='foreignkey')
    op.drop_column('wishes', 'feo_category_id')
    op.drop_constraint('fk_wishes_subsidy_id', 'wishes', type_='foreignkey')
    op.drop_column('wishes', 'subsidy_id')
