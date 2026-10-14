"""products.pack_quantity / products.pack_unit — упаковка (владелец, 14.10:
«когда товар меряется упаковками, должно быть количество в упаковке»).

Обе колонки NULL — валидны только когда products.unit — упаковочная единица
(app.services.units.is_pack_unit); у остальных товаров остаются NULL.
Идемпотентно: ADD COLUMN IF NOT EXISTS.

Revision ID: k1l2m3n4o5p6
Revises: f1a2b3c4d5e6
Create Date: 2026-10-14
"""
from alembic import op
from sqlalchemy import text

revision = 'k1l2m3n4o5p6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS pack_quantity NUMERIC(14, 3)"
    ))
    bind.execute(text(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS pack_unit VARCHAR(50)"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("ALTER TABLE products DROP COLUMN IF EXISTS pack_unit"))
    bind.execute(text("ALTER TABLE products DROP COLUMN IF EXISTS pack_quantity"))
