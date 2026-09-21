"""Решения по дублям строк ТЗ — purchases.tz_duplicate_decisions

Владелец (21.09, план corrections-21-09.md, раздел W3): повторяющиеся позиции
ТЗ («Огнетушитель — 2 шт»/«Огнетушитель — 3 шт», возможно в разных категориях
ФЭО) больше не склеиваются молча документом (_merge_identical_items удалена,
см. app.services.tz_items) — пользователь явно решает по каждой группе дублей
merge/keep через PUT /api/purchases/{id}/tz-duplicates. Решения переживают
закрытие карточки закупки и повторную генерацию документа, поэтому живут в
самой закупке, а не эфемерно на фронте.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  purchases:
    - tz_duplicate_decisions  JSONB  NULL — {group_key: 'merge'|'keep'}.
      NULL/отсутствие ключа = решения по этой группе ещё нет.

Downgrade — DROP COLUMN IF EXISTS (тоже идемпотентно).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision = 'r2t4v6x8z1b3'
down_revision = 'h1j3k5m7n9p1'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("purchases")}
    if "tz_duplicate_decisions" not in existing_cols:
        op.add_column(
            "purchases",
            sa.Column("tz_duplicate_decisions", postgresql.JSONB(), nullable=True),
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("purchases")}
    if "tz_duplicate_decisions" in existing_cols:
        op.drop_column("purchases", "tz_duplicate_decisions")
