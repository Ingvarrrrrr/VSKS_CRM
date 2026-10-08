"""Плановая позиция: feo_planned_items.plan_changed_at

Владелец 08.10.2026 (план binary-crunching-island.md, раздел 1): «Сейчас
закупка, при которой произошёл переход за лимит, определяется рандомно».
Причина — виновник превышения сортировался по created_at, а массовый перенос
позиций между категориями ФЭО (05-07.10) не трогает created_at, заведённый
при создании позиции из заявки (01.10) — «старая» дата на самом деле более
новое изменение плана.

plan_changed_at — момент, когда ВКЛАД позиции в план появился или изменился
(amount/quantity/unit_price/item_type/feo_category_id/is_active), а не момент
создания строки. Ставится ЕДИНСТВЕННЫМ местом — события SQLAlchemy модели
FeoPlannedItem (app/models/feo_planned_item.py, before_insert/before_update),
не этой миграцией за пределами бэкфилла.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  feo_planned_items:
    - plan_changed_at  TIMESTAMP  NOT NULL, server_default now()

Бэкфилл — ТОЛЬКО для существующих строк, где колонка только что добавлена:
plan_changed_at = created_at (владелец: «честная оговорка» про существующий
план — решение по умолчанию, пока не разведено скриптом
backend/scripts/set_plan_changed_at.py для конкретных закупок/субсидий).

Downgrade — DROP COLUMN IF EXISTS (идемпотентно)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'q2s4u6w8y0a2'
down_revision = 'd2f4h6j8k0m2'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "plan_changed_at" not in existing_cols:
        op.add_column(
            "feo_planned_items",
            sa.Column("plan_changed_at", sa.DateTime(), nullable=True),
        )
        op.execute("UPDATE feo_planned_items SET plan_changed_at = created_at WHERE plan_changed_at IS NULL")
        op.execute(
            "UPDATE feo_planned_items SET plan_changed_at = NOW() WHERE plan_changed_at IS NULL"
        )
        op.alter_column(
            "feo_planned_items", "plan_changed_at",
            nullable=False, server_default=sa.text("now()"),
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "plan_changed_at" in existing_cols:
        op.drop_column("feo_planned_items", "plan_changed_at")
