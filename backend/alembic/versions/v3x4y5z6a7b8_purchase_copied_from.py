"""purchases.copied_from_purchase_id — связь копии закупки с оригиналом
(задача «копирование закупок в другую субсидию»,
app/services/purchase_transfer/copy_one.py).

NULL у оригиналов и закупок, не связанных копией. FK ON DELETE SET NULL —
удаление оригинала не должно утягивать копию. Индекс — обратный поиск «копии
этой закупки» (GET /api/purchase-transfer/links/{id}) и поиск по номеру
оригинала в app/services/purchase_search.py.

Idempotent: ADD COLUMN IF NOT EXISTS + CREATE INDEX IF NOT EXISTS, под guard
на существование таблицы (тот же приём, что v2w3x4y5z6a7_purchases_source_key.py).

Revision ID: v3x4y5z6a7b8
Revises: n4o5p6q7r8s9
Create Date: 2026-10-16 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "v3x4y5z6a7b8"
down_revision = "n4o5p6q7r8s9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "purchases" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("purchases")}
    if "copied_from_purchase_id" not in cols:
        op.execute(sa.text(
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS copied_from_purchase_id INTEGER"
        ))
    fks = {fk["name"] for fk in inspector.get_foreign_keys("purchases")}
    if "fk_purchases_copied_from_purchase_id" not in fks:
        op.execute(sa.text(
            "ALTER TABLE purchases "
            "ADD CONSTRAINT fk_purchases_copied_from_purchase_id "
            "FOREIGN KEY (copied_from_purchase_id) REFERENCES purchases (id) ON DELETE SET NULL"
        ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_purchases_copied_from_purchase_id "
        "ON purchases (copied_from_purchase_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_purchases_copied_from_purchase_id"))
    op.execute(sa.text(
        "ALTER TABLE purchases DROP CONSTRAINT IF EXISTS fk_purchases_copied_from_purchase_id"
    ))
    op.execute(sa.text("ALTER TABLE purchases DROP COLUMN IF EXISTS copied_from_purchase_id"))
