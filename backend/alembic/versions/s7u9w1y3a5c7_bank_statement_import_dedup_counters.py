"""bank_statement_imports — счётчики повторной загрузки (дедуп legacy-строк)

Владелец, 05.10.2026: перезаливка выписки, у которой часть старых строк
загружена ДО появления колонки «Идентификатор документа» (external_doc_id
IS NULL), задваивала их — см. app/services/bank_payment_dedup.py. Новые
счётчики ответа POST /api/payments/imports: rows_updated/rows_unchanged/
rows_merged_legacy/rows_ambiguous.

Идемпотентно (ADD COLUMN IF NOT EXISTS) — alembic upgrade head гоняется при
каждом старте контейнера (migrate.py).

Revision ID: s7u9w1y3a5c7
Revises: r5t7v9x1z3b5
Create Date: 2026-10-05 01:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 's7u9w1y3a5c7'
down_revision = 'r5t7v9x1z3b5'
branch_labels = None
depends_on = None

_COLUMNS = ("rows_updated", "rows_unchanged", "rows_merged_legacy", "rows_ambiguous")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("bank_statement_imports")}
    for col in _COLUMNS:
        if col not in existing_cols:
            op.add_column(
                "bank_statement_imports",
                sa.Column(col, sa.Integer(), nullable=False, server_default="0"),
            )
            print(f"[s7u9w1y3a5c7] bank_statement_imports.{col} добавлен")


def downgrade() -> None:
    for col in _COLUMNS:
        op.execute(sa.text(f"ALTER TABLE bank_statement_imports DROP COLUMN IF EXISTS {col}"))
