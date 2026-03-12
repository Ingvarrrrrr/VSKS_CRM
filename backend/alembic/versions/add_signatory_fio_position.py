"""Add signatory_fio and signatory_position to contractors

Revision ID: add_signatory_fio_position
Revises: 
Create Date: 2026-03-12

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_signatory_fio_position'
down_revision = 'bcbeb8647a09'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('contractors', sa.Column('signatory_fio', sa.String(255), nullable=True))
    op.add_column('contractors', sa.Column('signatory_position', sa.String(255), nullable=True))

def downgrade() -> None:
    op.drop_column('contractors', 'signatory_fio')
    op.drop_column('contractors', 'signatory_position')
