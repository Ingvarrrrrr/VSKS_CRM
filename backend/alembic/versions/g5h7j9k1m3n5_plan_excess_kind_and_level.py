"""Согласование превышения плана ФЭО — независимость по виду (kind) и уровню (level)

Задача владельца (план ancient-prancing-music.md, раздел D, 2026-09-21): одно
approved-решение на узел раньше гасило ВСЕ виды превышения дерева сразу
(latest_approval_by_cat в app.services.feo_plan_tree, ДО этой миграции) —
теперь у каждого запроса есть kind (единственный источник видов/подписей —
app.services.plan_excess_kinds), и approved-решения по разным видам
независимы. feo_category_id теперь nullable — level='subsidy' (запись на
субсидию целиком, feo_category_id IS NULL) наравне с level='category'.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS / inspector-guard, см.
память проекта: migrate.py гонит upgrade head на старте прода, DDL должен
переживать повторный прогон):
  plan_excess_approvals:
    - kind              VARCHAR(40) NOT NULL DEFAULT 'legacy'
    - feo_category_id → nullable (ALTER COLUMN DROP NOT NULL)
    - индекс ix_plan_excess_approvals_cat_kind_created
      (subsidy_id, feo_category_id, kind, created_at)

ОБРАТНАЯ СОВМЕСТИМОСТЬ: все существующие записи получают kind='legacy' —
app.services.feo_plan_tree / app.services.tz_excess_approval / app.services.
contract_excess_approval трактуют approved legacy-запись как гасящую любой из
трёх старых видов узла (over_feo/fact_over_plan/plan_over_manual), см. их
docstring и plan_excess_kinds.LEGACY_FALLBACK_KINDS.

Downgrade — DROP INDEX/COLUMN IF EXISTS, feo_category_id обратно NOT NULL
(идемпотентно, тем же inspector-guard; пропускается, если в таблице уже есть
NULL-записи уровня subsidy — тогда откат руками).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'g5h7j9k1m3n5'
down_revision = 'f7g8h9i0j1k2'
branch_labels = None
depends_on = None


TABLE = "plan_excess_approvals"
INDEX_NAME = "ix_plan_excess_approvals_cat_kind_created"


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns(TABLE)}

    if "kind" not in existing_cols:
        op.add_column(
            TABLE,
            sa.Column("kind", sa.String(40), nullable=False, server_default="legacy"),
        )

    col = next((c for c in inspector.get_columns(TABLE) if c["name"] == "feo_category_id"), None)
    if col is not None and col.get("nullable") is False:
        op.alter_column(TABLE, "feo_category_id", nullable=True)

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(TABLE)}
    if INDEX_NAME not in existing_indexes:
        op.create_index(
            INDEX_NAME, TABLE,
            ["subsidy_id", "feo_category_id", "kind", "created_at"],
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(TABLE)}
    if INDEX_NAME in existing_indexes:
        op.drop_index(INDEX_NAME, table_name=TABLE)

    has_null_cat = conn.execute(
        sa.text(f"SELECT 1 FROM {TABLE} WHERE feo_category_id IS NULL LIMIT 1")
    ).first()
    col = next((c for c in inspector.get_columns(TABLE) if c["name"] == "feo_category_id"), None)
    if col is not None and col.get("nullable") is True and not has_null_cat:
        op.alter_column(TABLE, "feo_category_id", nullable=False)

    existing_cols = {c["name"] for c in inspector.get_columns(TABLE)}
    if "kind" in existing_cols:
        op.drop_column(TABLE, "kind")
