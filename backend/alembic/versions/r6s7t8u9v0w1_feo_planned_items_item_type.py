"""feo_planned_items.item_type — признак «Товар/Услуга/Работа» у плановой
позиции (блок 1, план zany-fluttering-mountain.md, 2026-08-14).

ПРИЧИНА. purchase_items/wish_items уже знают item_type (товар/услуга/работа),
а плановая позиция ФЭО (feo_planned_items) — нет, хотя план закупок должен
уметь показывать тот же признак и отдавать его вниз по потоку (заявка/закупка
наследуют тип плановой позиции, если у самих ещё не задан — см.
app/services/plan_autoassign.py::backfill_item_type_from_plan).

  feo_planned_items:
    item_type  VARCHAR(20) NULL — 'товар' | 'услуга' | 'работа' (нижний
               регистр, как в purchase_items.item_type/wish_items.item_type);
               нормализация свободного ввода — normalize_item_type() в
               app/routers/feo_planned_items.py.

Идемпотентно (ADD COLUMN IF NOT EXISTS) — безопасно против повторного прогона
и против check_schema (migrate.py гонит upgrade head на старте, конфликт DDL
роняет прод в 502).

Revision ID: r6s7t8u9v0w1
Revises: q5r6s7t8u9v0
Create Date: 2026-08-14 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'r6s7t8u9v0w1'
down_revision = 'q5r6s7t8u9v0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'feo_planned_items' not in inspector.get_table_names():
        return
    op.execute(sa.text(
        "ALTER TABLE feo_planned_items ADD COLUMN IF NOT EXISTS "
        "item_type VARCHAR(20)"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'feo_planned_items' not in inspector.get_table_names():
        return
    op.execute(sa.text(
        "ALTER TABLE feo_planned_items DROP COLUMN IF EXISTS item_type"
    ))
