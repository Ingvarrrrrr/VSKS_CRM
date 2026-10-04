"""Плановая позиция: статус «нужности» (feo_planned_items.need_level)

Владелец (04.10.2026, план .planning/quick/2026-10-04-sheet-ideas): у плановой
позиции (FeoPlannedItem) два статуса —
  'likely'       — «Скорее всего понадобится» (умолчание, ВСЕ существующие
                   позиции трактуются так же, как и раньше — никакого
                   поведенческого сдвига для них).
  'nice_to_have' — «Хотелось бы, но можно и отказаться».

Подписи/константы — ЕДИНОЕ место, app.services.plan_need_level (ПРАВИЛО №6).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  feo_planned_items:
    - need_level  VARCHAR(20)  NOT NULL DEFAULT 'likely'

Downgrade — DROP COLUMN IF EXISTS (тоже идемпотентно).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'p1q3r5s7t9v1'
down_revision = 'n7p9q1r3s5t7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "need_level" not in existing_cols:
        op.add_column(
            "feo_planned_items",
            sa.Column("need_level", sa.String(20), nullable=False, server_default="likely"),
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "need_level" in existing_cols:
        op.drop_column("feo_planned_items", "need_level")
