"""Журнал изменений ФЭО (волна 1 из 3): source/source_ref в entity_changes + feo_import_runs

Владелец (22.09): «Импорт ФЭО не оставляет записи, кто загрузил файл и что он
перезаписал. А также если кто-то менял плановые позиции в ФЭО или вносил
новые, независимо от способа внесения. Если плановая появилась из заявки, то
пишется, на основании какой заявки».

Вторую таблицу истории не заводим (Правило №6) — расширяем существующий
entity_changes (см. app/models/entity_change.py, app/routers/entity_changes.py):
    source      — откуда пришло изменение ('manual'|'import'|'wish'|'purchase'|
                  'autoassign'|'collapse', см. app/services/feo_history.py::SOURCES).
    source_ref  — id сущности-источника: для source='import' — id строки
                  feo_import_runs; для 'wish' — id заявки; для 'purchase' — id
                  закупки; для 'manual'/'autoassign'/'collapse' обычно NULL.

feo_import_runs — один прогон импорта Excel-файла ФЭО (кто загрузил, когда,
сколько создано/обновлено/пропущено). Модель — см. app/models/feo_import_run.py
(докстринг там объясняет, почему она НЕ зарегистрирована в
app/models/__init__.py — файл занят параллельной сессией 152-ФЗ).

Идемпотентно — inspector-guard на add_column/create_table, т.к. на старте
контейнера гонится `alembic upgrade head`, а рядом check_schema делает
create_all для новых таблиц (конфликт DDL иначе валит бэкенд в 502, см.
соседние миграции, например d3e5f7g9h1j3).

Волна 2 (следующая): расстановка вызовов record_*() из feo_history.py в
точках изменения плановых позиций/категорий и в движке импорта.
Волна 3: UI (лента истории на карточке позиции/категории).

Revision ID: t6v8x1z3b5d7
Revises: r2t4v6x8z1b3
Create Date: 2026-09-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 't6v8x1z3b5d7'
down_revision = 'r2t4v6x8z1b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    existing_cols = {c["name"] for c in insp.get_columns("entity_changes")}
    if "source" not in existing_cols:
        op.add_column("entity_changes", sa.Column("source", sa.String(20), nullable=True))
    if "source_ref" not in existing_cols:
        op.add_column("entity_changes", sa.Column("source_ref", sa.Integer(), nullable=True))

    if not insp.has_table("feo_import_runs"):
        op.create_table(
            "feo_import_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("subsidy_id", sa.Integer(), sa.ForeignKey("subsidies.id", ondelete="SET NULL"), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("user_name", sa.String(200), nullable=True),
            sa.Column("filename", sa.String(500), nullable=True),
            sa.Column("sheet_name", sa.String(200), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("comments_created", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("warnings_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("summary", postgresql.JSONB(), nullable=True),
        )
        op.create_index("ix_feo_import_runs_subsidy_id", "feo_import_runs", ["subsidy_id"])


def downgrade() -> None:
    op.drop_table("feo_import_runs")
    with op.batch_alter_table("entity_changes") as batch_op:
        batch_op.drop_column("source_ref")
        batch_op.drop_column("source")
