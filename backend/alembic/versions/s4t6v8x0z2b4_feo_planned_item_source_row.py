"""feo_planned_items.source_row — номер строки файла загрузки плана

Владелец (12.10.2026, план lazy-swimming-hollerith.md, п.4г): вместо
нумерации «2.»/«4.» в таблице позиций — мелкая подпись «строка N файла» у
каждой позиции (у частей объединённой позиции номер уже есть в
parts[].row, см. миграцию r3s5u7w9y1a3). Позиции, заведённые в GALA вручную
(не загрузкой плана), source_row не получают (NULL).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  feo_planned_items:
    - source_row  INTEGER  NULL — номер строки файла, которым был загружен
      план (feo_import_duplicates.py::_upsert_one). У объединённой позиции —
      номер ПЕРВОЙ строки группы (части несут свои номера в parts[].row).

Кнопка «Убрать номера строк файла» (администратор+) обнуляет source_row у
всех позиций субсидии и parts[].row (parts[].key НЕ трогает) — отдельного
поля для этого не требуется, апдейт идёт по существующим колонкам.

Downgrade — DROP COLUMN IF EXISTS (идемпотентно)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 's4t6v8x0z2b4'
down_revision = 'r3s5u7w9y1a3'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    fpi_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "source_row" not in fpi_cols:
        op.add_column(
            "feo_planned_items",
            sa.Column("source_row", sa.Integer(), nullable=True),
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    fpi_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "source_row" in fpi_cols:
        op.drop_column("feo_planned_items", "source_row")
