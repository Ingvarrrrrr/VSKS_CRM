"""Справочник категорий закупки + связь many-to-many с товарами

Владелец (2026-09-16): у товара ДВЕ категории — «категория товара»
(products.category, уже существует) и «категории закупки» (несколько,
отдельный справочник, владелец ведёт сам). Пример: краги пожарного —
категория товара «СИЗ», категории закупки «Пожарное оборудование» и «СИЗ».

Создаёт (идемпотентно, под inspector.has_table() guard, по образцу
r4t6v8x0z2b4_staff_location_requests.py):

  - purchase_categories:
      name        VARCHAR(200) NOT NULL UNIQUE
      sort_order  INTEGER NOT NULL DEFAULT 0
      is_active   BOOLEAN NOT NULL DEFAULT true
      created_at  TIMESTAMPTZ NOT NULL DEFAULT now()

  - product_purchase_categories (M2M, без своих полей):
      product_id            FK products.id ON DELETE CASCADE
      purchase_category_id  FK purchase_categories.id ON DELETE CASCADE
      PK (product_id, purchase_category_id)

Revision ID: s3u5w7y9a1c3
Revises: c9e1g3i5k7m9
Create Date: 2026-09-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 's3u5w7y9a1c3'
down_revision = 'c9e1g3i5k7m9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table("purchase_categories"):
        op.create_table(
            "purchase_categories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False, unique=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
        )

    if not insp.has_table("product_purchase_categories"):
        op.create_table(
            "product_purchase_categories",
            sa.Column("product_id", sa.Integer(),
                      sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("purchase_category_id", sa.Integer(),
                      sa.ForeignKey("purchase_categories.id", ondelete="CASCADE"), primary_key=True),
        )
        op.create_index(
            "ix_product_purchase_categories_category",
            "product_purchase_categories", ["purchase_category_id"],
        )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS product_purchase_categories"))
    op.execute(sa.text("DROP TABLE IF EXISTS purchase_categories"))
