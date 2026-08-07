"""wish_items: feo_planned_item_match_confirmed (Шаг 4 плана
zany-fluttering-mountain.md — подсказка «похожая плановая позиция» с
подтверждением, по образцу purchase_items.match_confirmed).

Флаг фиксирует, что привязку к плановой позиции (feo_planned_item_id) выбрал
человек, подтвердив предложенного по имени кандидата (POST
/feo-planned-items/confirm-wish-plan-match), а не автоподстановка. Default
FALSE — простые/старые позиции (в т.ч. созданные автозаведением плана при
согласовании, wishes.py._auto_assign_planned_items) остаются неподтверждёнными;
это ожидаемо, флаг не гейтит бизнес-логику (см. докстринг эндпоинта), только
UI-признак «откуда взялась привязка».

Идемпотентно (ADD COLUMN IF NOT EXISTS) — безопасно против повторного прогона
и против check_schema.

Revision ID: l5m6n7o8p9q0
Revises: j1k2l3m4n5o6
Create Date: 2026-08-07 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'l5m6n7o8p9q0'
down_revision = 'j1k2l3m4n5o6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'wish_items' not in inspector.get_table_names():
        return
    op.execute(sa.text(
        "ALTER TABLE wish_items ADD COLUMN IF NOT EXISTS "
        "feo_planned_item_match_confirmed BOOLEAN NOT NULL DEFAULT FALSE"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'wish_items' not in inspector.get_table_names():
        return
    op.execute(sa.text(
        "ALTER TABLE wish_items DROP COLUMN IF EXISTS feo_planned_item_match_confirmed"
    ))
