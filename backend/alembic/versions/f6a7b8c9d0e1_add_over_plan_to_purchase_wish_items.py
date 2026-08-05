"""purchase_items/wish_items: over_plan flag (сверх плана ФЭО)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-05 00:00:00.000000

Плановая позиция (конечный элемент дерева ФЭО с заполненными
planned_quantity/planned_amount) имеет фиксированную плановую сумму. Позиции
закупок/заявок, отнесённые к ней, до сих пор всегда считались «расходующими»
этот план — не было способа отметить позицию как «сверх плана» (когда
фактическая потребность превышает изначально запланированную сумму, но
закупку всё равно нужно провести и учесть отдельно от «расходования»
исходного лимита).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  purchase_items:
    - over_plan BOOLEAN NOT NULL DEFAULT false
  wish_items:
    - over_plan BOOLEAN NOT NULL DEFAULT false

Семантика: false — позиция РАСХОДУЕТ план своего конечного элемента ФЭО;
true — «сверх плана», прибавляется к плановой сумме (не вычитается из
исходного лимита конечного элемента).

downgrade(): DROP COLUMN IF EXISTS на обеих таблицах.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS over_plan BOOLEAN NOT NULL DEFAULT false"
    ))
    op.execute(sa.text(
        "ALTER TABLE wish_items ADD COLUMN IF NOT EXISTS over_plan BOOLEAN NOT NULL DEFAULT false"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE purchase_items DROP COLUMN IF EXISTS over_plan"))
    op.execute(sa.text("ALTER TABLE wish_items DROP COLUMN IF EXISTS over_plan"))
