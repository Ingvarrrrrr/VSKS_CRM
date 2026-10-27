"""product_barcodes — штрихкод (EAN-13/EAN-8/UPC-12/GTIN-14) как главный
ключ сведения одной карточки товара из разных магазинов (решение владельца,
27.10.2026). Один товар может иметь несколько штрихкодов; один штрихкод
может встретиться у нескольких карточек до слияния (UNIQUE только на
(product_id, barcode) — не на barcode одном, см. app/models/product_barcode.py
и app/services/products_import_match.py, критерий (0.25)).

Идемпотентно (ПРАВИЛО №6, тот же приём, что у соседних миграций
a4b6c8d0e2f4/z1a2b3c4d5e6) — create_table/create_index только если их ещё
нет (inspector-guard). Downgrade — DROP TABLE IF EXISTS (каскадом уносит
индекс/constraint).

Revision ID: b8c0d2e4f6a8
Revises: a4b6c8d0e2f4
Create Date: 2026-10-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "b8c0d2e4f6a8"
down_revision = "a4b6c8d0e2f4"
branch_labels = None
depends_on = None

_TABLE = "product_barcodes"
_BARCODE_INDEX = "ix_product_barcodes_barcode"
_UNIQUE_NAME = "uq_product_barcodes_product_barcode"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "product_id", sa.Integer,
                sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("barcode", sa.String(14), nullable=False),
            sa.Column(
                "contractor_id", sa.Integer,
                sa.ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.UniqueConstraint("product_id", "barcode", name=_UNIQUE_NAME),
        )

    inspector = inspect(conn)
    existing_indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _BARCODE_INDEX not in existing_indexes:
        op.create_index(_BARCODE_INDEX, _TABLE, ["barcode"])
    if "ix_product_barcodes_product_id" not in existing_indexes:
        op.create_index("ix_product_barcodes_product_id", _TABLE, ["product_id"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
