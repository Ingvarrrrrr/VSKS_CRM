"""product_price_history.store_article — артикул товара в КОНКРЕТНОМ
магазине (владелец, 27.10.2026, задача manufacturer_article/store_article):
item.article смешивал два разных понятия — артикул производителя (одинаковый
во всех магазинах, например 14054DEK у МПО Электромонтаж) и номер товара в
конкретном магазине (у Сима-ленда 4878510, у Бауцентра 705003235). Новое
item.manufacturer_article пишется в Product.article (см. products_import_
apply.py); item.store_article — специфичен для магазина и не имеет смысла на
уровне товара, пишется построчно в историю цены (ProductPriceHistory), рядом
с её же contractor_id (тем же магазином).

region у product_price_history уже существует (clever-bouncing-lantern.md,
Часть 2) — эта миграция добавляет ТОЛЬКО store_article + частичный индекс
(contractor_id, store_article) WHERE store_article IS NOT NULL — ускоряет
backend/app/services/products_import_match.py::ProductMatchIndex (новый
первый критерий сопоставления «тот же магазин + тот же store_article»).

Идемпотентно: ADD COLUMN IF NOT EXISTS + CREATE INDEX IF NOT EXISTS (через
inspector-guard, как у соседних миграций z1a2b3c4d5e6/z1a2b3c4d5e6).
Downgrade — DROP INDEX/DROP COLUMN IF EXISTS.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "a4b6c8d0e2f4"
down_revision = "z2a3b4c5d6e7"
branch_labels = None
depends_on = None

_INDEX_NAME = "ix_product_price_history_contractor_store_article"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("product_price_history")}
    if "store_article" not in existing_cols:
        op.add_column(
            "product_price_history",
            sa.Column("store_article", sa.String(200), nullable=True),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("product_price_history")}
    if _INDEX_NAME not in existing_indexes:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {_INDEX_NAME} "
            "ON product_price_history (contractor_id, store_article) "
            "WHERE store_article IS NOT NULL"
        )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME}")
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("product_price_history")}
    if "store_article" in existing_cols:
        op.drop_column("product_price_history", "store_article")
