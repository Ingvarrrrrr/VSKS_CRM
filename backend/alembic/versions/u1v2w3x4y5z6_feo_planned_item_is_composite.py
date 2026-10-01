"""Плановая позиция: признак «составная» (feo_planned_items.is_composite)

Владелец, решение по задаче «Составная плановая позиция»: одна плановая
позиция (напр. «Проживание и питание участников…», 133 чел., сумма S / цена
за единицу P) закрывается в договоре ДВУМЯ строками закупки — «Услуги по
организации проживания» 133×1265 и «Услуга по организации питания» 133×735,
обе привязаны (PurchaseItem.feo_planned_item_id) к ОДНОЙ плановой позиции.

ДО этой миграции контроль «ТЗ не выше плана» (assert_tz_batch_not_over_plan,
app/services/feo_plan_tz_checks.py) и расход плановой позиции
(planned_item_consumption, app/services/feo_plan_fact.py) складывали
количество строк группы (133+133=266) против плана в 133 → ложный 409
«ТЗ выше плана» и residual_quantity = -133, хотя по факту обе строки описывают
ОДНО и то же количество человек, просто две услуги.

is_composite=True переключает агрегацию ГРУППЫ строк одной закупки на той же
плановой позиции (ПРАВИЛО №6 — одна формула, см. composite_group_metrics в
app/services/feo_plan_common.py):
  - количество группы = MAX количеств строк (не сумма);
  - цена за единицу группы = СУММА цен за единицу строк (не максимум) —
    сравнивается с unit_price плана (1265+735 против 2000);
  - сумма группы — без изменений (сумма сумм, как и раньше).

is_composite=False (дефолт) — поведение не меняется ни на копейку: старая
формула (кол-во суммируется, цена — максимум по группе) продолжает работать
для всех существующих позиций.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  feo_planned_items:
    - is_composite  BOOLEAN NOT NULL DEFAULT FALSE

Downgrade — DROP COLUMN IF EXISTS (тоже идемпотентно).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'u1v2w3x4y5z6'
down_revision = 'a7c9e1f3b5d7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "is_composite" not in existing_cols:
        op.add_column(
            "feo_planned_items",
            sa.Column(
                "is_composite", sa.Boolean(), nullable=False,
                server_default=sa.text("FALSE"),
            ),
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "is_composite" in existing_cols:
        op.drop_column("feo_planned_items", "is_composite")
