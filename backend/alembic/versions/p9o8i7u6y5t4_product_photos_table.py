"""Фото товара — отдельная таблица product_photos

Владелец (26.10.2026): фото каталога носят информационный характер и не
должны раздувать ежедневный бэкап БД. Переносим bytea из products.photo_data
в новую таблицу product_photos (product_id PK/FK CASCADE, data, mime, size,
updated_at), чтобы pg_backup.sh мог исключить её данные из основного
daily-дампа и бэкапить фото отдельно (см. scripts/ops/pg_backup.sh).

Upgrade:
  1. CREATE TABLE IF NOT EXISTS product_photos.
  2. INSERT…SELECT переносит существующие байты из products как есть, БЕЗ
     пересжатия (это отдельно делает scripts/recompress_product_photos.py).
  3. DROP COLUMN products.photo_data (photo_mime/photo_size остаются на
     products как дёшевый кэш метаданных).

Downgrade — обратный перенос: добавляет products.photo_data, копирует байты
обратно из product_photos, затем дропает таблицу. Идемпотентно в обе стороны
(inspector-guard на существование колонки/таблицы).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'p9o8i7u6y5t4'
down_revision = 'q2w3e4r5t6y7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "product_photos" not in existing_tables:
        op.create_table(
            "product_photos",
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("data", sa.LargeBinary(), nullable=False),
            sa.Column("mime", sa.String(50), nullable=True),
            sa.Column("size", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("product_id"),
        )

    products_cols = {c["name"] for c in inspector.get_columns("products")}
    if "photo_data" in products_cols:
        conn.execute(sa.text(
            """
            INSERT INTO product_photos (product_id, data, mime, size, updated_at)
            SELECT id, photo_data, photo_mime, photo_size, now()
            FROM products
            WHERE photo_data IS NOT NULL
            ON CONFLICT (product_id) DO NOTHING
            """
        ))
        op.drop_column("products", "photo_data")


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    products_cols = {c["name"] for c in inspector.get_columns("products")}
    existing_tables = set(inspector.get_table_names())

    if "photo_data" not in products_cols:
        op.add_column("products", sa.Column("photo_data", sa.LargeBinary(), nullable=True))

    if "product_photos" in existing_tables:
        conn.execute(sa.text(
            """
            UPDATE products p
            SET photo_data = pp.data
            FROM product_photos pp
            WHERE pp.product_id = p.id
            """
        ))
        op.drop_table("product_photos")
