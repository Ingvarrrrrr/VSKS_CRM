"""Phase 27: delivery_items table

Revision ID: f6a8b0c2d4e6
Revises: e5f7a9b1c3d5
Create Date: 2026-11-21 14:10:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "f6a8b0c2d4e6"
down_revision = "e5f7a9b1c3d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "delivery_items" not in tables:
        op.create_table(
            "delivery_items",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column(
                "purchase_id",
                sa.Integer(),
                sa.ForeignKey("purchases.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "contract_item_id",
                sa.Integer(),
                sa.ForeignKey("contract_items.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column(
                "purchase_item_id",
                sa.Integer(),
                sa.ForeignKey("purchase_items.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column(
                "product_id",
                sa.Integer(),
                sa.ForeignKey("products.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("unit", sa.String(50), nullable=True),
            sa.Column("qty", sa.Numeric(14, 4), nullable=False, server_default=sa.text("0")),
            sa.Column("unit_price", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("total", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("delivery_date", sa.Date(), nullable=True),
            sa.Column("doc_number", sa.String(255), nullable=True),
            sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'pending'")),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("NOW()"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "delivery_items" in tables:
        op.drop_table("delivery_items")
