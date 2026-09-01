"""products.unit — единица измерения товара + бэкфилл из истории закупок

Владелец (2026-09-01): «Как блядь нет единицы измерения — добавить! И при
следующем импорте данных из экселя, там где нет этих данных, добавить в
каждую карточку товара. Должно браться из БД по товарам. Если две разные
единицы измерения записаны для какого-то товара, то ничего не надо
указывать — никакой единицы измерения».

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  products:
    - unit  VARCHAR(50)  NULL

Бэкфилл (в этой же миграции, тоже идемпотентный — WHERE products.unit IS
NULL/пусто, повторный прогон ничего не меняет): для каждого товара
собираются единицы измерения (purchase_items.unit, непустые, обрезанные по
пробелам) из ВСЕХ его позиций закупок. Если единственная различная — она
записывается в products.unit. Если встречается ДВЕ и больше различных —
products.unit остаётся NULL (см. app/services/product_unit.py — та же логика
переиспользуется импортом Excel и /api/feo-planned-items/product-hint).

Revision ID: f25e7fa19cbc
Revises: v4w5x6y7z8a9
Create Date: 2026-09-01 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'f25e7fa19cbc'
down_revision = 'af3caa6082ed'
branch_labels = None
depends_on = None


def _cols(inspector, table: str) -> set:
    return {c['name'] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'products' not in inspector.get_table_names():
        return

    existing = _cols(inspector, 'products')
    if 'unit' not in existing:
        op.add_column('products', sa.Column('unit', sa.String(length=50), nullable=True))

    if 'purchase_items' not in inspector.get_table_names():
        return

    # Бэкфилл: единственная встречавшаяся ЕИ по товару → products.unit;
    # разнобой (2+ различных нормализованных значений) — оставляем NULL.
    op.execute(sa.text("""
        WITH normalized AS (
            SELECT product_id, btrim(unit) AS unit
            FROM purchase_items
            WHERE product_id IS NOT NULL
              AND unit IS NOT NULL
              AND btrim(unit) <> ''
        ),
        distinct_units AS (
            SELECT product_id,
                   COUNT(DISTINCT unit) AS distinct_cnt,
                   MIN(unit) AS only_unit
            FROM normalized
            GROUP BY product_id
        )
        UPDATE products p
        SET unit = d.only_unit
        FROM distinct_units d
        WHERE p.id = d.product_id
          AND d.distinct_cnt = 1
          AND (p.unit IS NULL OR btrim(p.unit) = '')
    """))


def downgrade() -> None:
    op.execute(sa.text('ALTER TABLE products DROP COLUMN IF EXISTS unit'))
