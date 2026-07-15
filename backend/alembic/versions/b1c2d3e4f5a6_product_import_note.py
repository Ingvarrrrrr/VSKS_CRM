"""products.import_note — примечание об импорте (кто загрузил, каким способом, когда)

Заполняется при импорте товаров/позиций из файлов; показывается в карточке товара.

Idempotent: ADD COLUMN IF NOT EXISTS под inspector-guard.

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-07-15 18:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'b1c2d3e4f5a6'
down_revision = 'a0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'products' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('products')}
    if 'import_note' not in cols:
        op.execute(sa.text("ALTER TABLE products ADD COLUMN IF NOT EXISTS import_note TEXT"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS import_note"))
