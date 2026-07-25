"""add structured delivery address fields to purchases

Revision ID: o2p3q4r5s6t7
Revises: n1o2p3q4r5s6
Create Date: 2026-07-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'o2p3q4r5s6t7'
down_revision = 'n1o2p3q4r5s6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c['name'] for c in insp.get_columns('purchases')}
    if 'delivery_region' not in cols:
        op.add_column('purchases', sa.Column('delivery_region', sa.String(100), nullable=True))
    if 'delivery_city' not in cols:
        op.add_column('purchases', sa.Column('delivery_city', sa.String(200), nullable=True))
    if 'delivery_street' not in cols:
        op.add_column('purchases', sa.Column('delivery_street', sa.String(300), nullable=True))
    if 'delivery_house' not in cols:
        op.add_column('purchases', sa.Column('delivery_house', sa.String(50), nullable=True))
    if 'delivery_building' not in cols:
        op.add_column('purchases', sa.Column('delivery_building', sa.String(50), nullable=True))
    if 'delivery_postcode' not in cols:
        op.add_column('purchases', sa.Column('delivery_postcode', sa.String(20), nullable=True))


def downgrade():
    op.drop_column('purchases', 'delivery_postcode')
    op.drop_column('purchases', 'delivery_building')
    op.drop_column('purchases', 'delivery_house')
    op.drop_column('purchases', 'delivery_street')
    op.drop_column('purchases', 'delivery_city')
    op.drop_column('purchases', 'delivery_region')
