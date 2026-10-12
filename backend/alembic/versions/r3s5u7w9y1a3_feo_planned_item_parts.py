"""Состав объединённой плановой позиции: feo_planned_items.parts,
purchase_items.feo_plan_part_key

Владелец (12.10.2026, план merged-item-parts.md): при загрузке плана
«Объединить в одну» несколько строк файла (напр. «Gaz A22R35 Х920АЕ 180»:
352 400 = 317 400 + 20 000 + 10 000 + 5 000) схлопываются в одну FeoPlannedItem
— раньше состав терялся, хотя это разные закупки внутри одной позиции.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  feo_planned_items:
    - parts  JSONB  NOT NULL DEFAULT '[]'::jsonb
      [{key, row, qty, unit, unit_price, amount}] — key = номер строки файла
      строкой («151»); у НЕобъединённых позиций — []. Заполняется и
      поддерживается ТОЛЬКО app/services/feo_import_duplicates.py (merge при
      загрузке плана) — ручного редактирования состава в GALA нет (см. план).
  purchase_items:
    - feo_plan_part_key  VARCHAR(32)  NULL — к какой части объединённой
      позиции относится строка закупки (заполняется импортом факта,
      app/services/historical_fact_import/).

Downgrade — DROP COLUMN IF EXISTS (идемпотентно)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import inspect


revision = 'r3s5u7w9y1a3'
down_revision = 'q2s4u6w8y0a2'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    fpi_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "parts" not in fpi_cols:
        op.add_column(
            "feo_planned_items",
            sa.Column("parts", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        )

    pi_cols = {c["name"] for c in inspector.get_columns("purchase_items")}
    if "feo_plan_part_key" not in pi_cols:
        op.add_column(
            "purchase_items",
            sa.Column("feo_plan_part_key", sa.String(length=32), nullable=True),
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    pi_cols = {c["name"] for c in inspector.get_columns("purchase_items")}
    if "feo_plan_part_key" in pi_cols:
        op.drop_column("purchase_items", "feo_plan_part_key")

    fpi_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "parts" in fpi_cols:
        op.drop_column("feo_planned_items", "parts")
