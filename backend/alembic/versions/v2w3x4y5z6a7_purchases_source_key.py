"""purchases.source_key — ключ строки источника импорта факта (план
composed-noodling-lampson.md, 16.10.2026, раздел 4 «Повторная заливка того
же файла»).

Повторная заливка того же файла GoodsService ищет уже загруженную закупку по
(subsidy_id, source_key), а не создаёт её заново — ключ строится как
`gs:{ИНН или нормализованный контрагент}:{номер закупки D}` (у заказа внутри
рамочной закупки — ещё `:{номер заказа E}`), см. app/services/
historical_fact_import/contract_groups.py::build_source_key.

Idempotent: ADD COLUMN IF NOT EXISTS + индекс CREATE INDEX IF NOT EXISTS, под
guard на существование таблицы/колонки (тот же приём, что a0b1c2d3e4f5_org_
parent_org_id.py).

Backfill: закупки, уже загруженные разовым скриптом backend/scripts/
fadm_sheet_load/ (ФАДМ 2026_3), несут пометку task_comment вида «Таблица
GoodsService: закупка {D} (ИНН {ИНН})» или «... (рамочный договор, ИНН
{ИНН})» (см. sheet_v2_build.py::build_single/build_framework) — разбираем D и
ИНН оттуда и заполняем source_key тем же форматом `gs:{ИНН}:{D}`, чтобы
повторная заливка узнала эти закупки, не задваивая их.

Revision ID: v2w3x4y5z6a7
Revises: v3x4y5z6a7b8
Create Date: 2026-10-16 00:00:00.000000
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "v2w3x4y5z6a7"
down_revision = "v3x4y5z6a7b8"
branch_labels = None
depends_on = None

_TASK_COMMENT_RE = re.compile(
    r"Таблица GoodsService:\s*закупка\s+(?P<no>\S+)\s*\([^)]*ИНН\s+(?P<inn>\d+)\)",
    re.IGNORECASE,
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "purchases" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("purchases")}
    if "source_key" not in cols:
        op.execute(sa.text(
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS source_key VARCHAR(200)"
        ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_purchases_subsidy_source_key "
        "ON purchases (subsidy_id, source_key)"
    ))

    # Backfill из task_comment — только строки, уже заведённые разовым
    # скриптом (см. docstring выше); идемпотентно — WHERE source_key IS NULL,
    # повторный прогон миграции (или ручной re-run) не трогает уже заполненные.
    rows = bind.execute(sa.text(
        "SELECT id, task_comment FROM purchases "
        "WHERE source_key IS NULL AND task_comment LIKE 'Таблица GoodsService:%'"
    )).fetchall()
    for row_id, task_comment in rows:
        m = _TASK_COMMENT_RE.search(task_comment or "")
        if not m:
            continue
        key = f"gs:{m.group('inn')}:{m.group('no')}"
        bind.execute(
            sa.text("UPDATE purchases SET source_key = :key WHERE id = :id"),
            {"key": key, "id": row_id},
        )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_purchases_subsidy_source_key"))
    op.execute(sa.text("ALTER TABLE purchases DROP COLUMN IF EXISTS source_key"))
