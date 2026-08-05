"""products.country_origin: «Россия» → «РФ»

Владелец (2026-08-05): каталог должен использовать «РФ» вместо «Россия» —
короче, занимает меньше места в колонке, и совпадает с термином, уже
используемым в позициях закупки (purchase_items/wish_items используют «РФ»
как значение по умолчанию на фронте). Модельный default тоже переведён на
«РФ» (см. app/models/product.py), эта миграция подтягивает существующие
строки каталога товаров под новый термин.

Idempotent: UPDATE только строк с точным значением 'Россия', повторный
прогон ничего не меняет.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-08-05 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'products' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('products')}
    if 'country_origin' not in cols:
        return
    op.execute(sa.text("UPDATE products SET country_origin = 'РФ' WHERE country_origin = 'Россия'"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'products' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('products')}
    if 'country_origin' not in cols:
        return
    op.execute(sa.text("UPDATE products SET country_origin = 'Россия' WHERE country_origin = 'РФ'"))
