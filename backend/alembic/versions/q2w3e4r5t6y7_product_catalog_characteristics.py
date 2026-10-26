"""Карточка товара: структурированные характеристики + производитель/артикул

Владелец (26.10.2026): каталог товаров должен уметь показывать структурированные
характеристики (пара «название — значение», опционально с единицей — высота,
цвет, серия, IP и т.п.), а также отдельно производителя и артикул, а не
сваливать всё текстом в description. Карточка товара сейчас только ПОКАЗЫВАЕТ
эти поля (read-only блок, см. ProductFormDialog.vue) — загрузчик, который их
будет заполнять (конвертеры из прайсов поставщиков в формат GALA, см.
app/services/catalog_gala/), придёт отдельным шагом позже; эта миграция только
готовит место в схеме.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  products:
    - characteristics  JSONB         NULL — список объектов
      [{"name": "...", "value": "...", "unit": "..."}], порядок как у
      поставщика; NULL/[] — характеристик нет.
    - manufacturer     VARCHAR(300)  NULL — производитель.
    - article          VARCHAR(200)  NULL — артикул/номер по каталогу поставщика.

Downgrade — DROP COLUMN IF EXISTS (тоже идемпотентно).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import inspect


revision = 'q2w3e4r5t6y7'
down_revision = 'h2j4l6n8p0r2'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("products")}
    if "characteristics" not in existing_cols:
        op.add_column(
            "products",
            sa.Column("characteristics", JSONB, nullable=True),
        )
    if "manufacturer" not in existing_cols:
        op.add_column(
            "products",
            sa.Column("manufacturer", sa.String(300), nullable=True),
        )
    if "article" not in existing_cols:
        op.add_column(
            "products",
            sa.Column("article", sa.String(200), nullable=True),
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("products")}
    if "article" in existing_cols:
        op.drop_column("products", "article")
    if "manufacturer" in existing_cols:
        op.drop_column("products", "manufacturer")
    if "characteristics" in existing_cols:
        op.drop_column("products", "characteristics")
