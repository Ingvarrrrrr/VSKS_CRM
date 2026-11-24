"""add cell_marks table

Revision ID: c3e5a7b9d1f3
Revises: f6a8b0c2d4e6
Create Date: 2026-11-23 21:15:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "c3e5a7b9d1f3"
down_revision = "f6a8b0c2d4e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "cell_marks" not in tables:
        op.create_table(
            "cell_marks",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("group_id", sa.String(36), nullable=False, index=True),
            sa.Column("entity_type", sa.String(40), nullable=False, index=True),
            sa.Column("entity_id", sa.Integer(), nullable=False, index=True),
            sa.Column("field_name", sa.String(80), nullable=False, server_default="*", default="*"),
            sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True),
            sa.Column("subsidy_id", sa.Integer(), sa.ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=True, index=True),
            sa.Column("color", sa.String(24), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("visibility", sa.String(16), nullable=False, server_default="shared"),
            sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false"), index=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("resolved_by_name", sa.String(255), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("created_by_name", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        # Composite index for entity lookup (single-column indexes created by index=True above)
        op.create_index("ix_cell_marks_lookup", "cell_marks", ["entity_type", "entity_id", "field_name"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "cell_marks" in tables:
        op.drop_table("cell_marks")
