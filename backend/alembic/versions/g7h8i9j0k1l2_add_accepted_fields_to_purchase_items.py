"""purchase_items: accepted_name/accepted_quantity/accepted_unit («Приняли»)

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-05 00:00:00.000000

Пятая стадия жизненного цикла позиции («что приняли», в терминологии владельца —
«...в голубой обложке») до сих пор не имела собственных полей: ФЭО → План →
Что выставляли на закупку (purchase_items.item_name/quantity) → Номенклатура
подрядчика (contract_items.name/quantity, source_item_id → purchase_items.id) →
… и дальше поля отсутствовали. Деньги этой стадии уже есть (final_unit_price/
final_total), не хватало наименования/количества/единицы измерения по факту
приёмки.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS) на purchase_items:
  - accepted_name TEXT NULL
  - accepted_quantity NUMERIC(15,4) NULL
  - accepted_unit VARCHAR(50) NULL

Автозаполняется при переходе закупки в delivered (см.
app/routers/purchase_transitions.py) из contract_items (по source_item_id),
либо из самой purchase_items, если договорной строки нет. Дальше правится
вручную через PATCH позиции / карточку закупки.

downgrade(): DROP COLUMN IF EXISTS на всех трёх колонках.
"""
from alembic import op
import sqlalchemy as sa

revision = 'g7h8i9j0k1l2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS accepted_name TEXT"
    ))
    op.execute(sa.text(
        "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS accepted_quantity NUMERIC(15,4)"
    ))
    op.execute(sa.text(
        "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS accepted_unit VARCHAR(50)"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE purchase_items DROP COLUMN IF EXISTS accepted_name"))
    op.execute(sa.text("ALTER TABLE purchase_items DROP COLUMN IF EXISTS accepted_quantity"))
    op.execute(sa.text("ALTER TABLE purchase_items DROP COLUMN IF EXISTS accepted_unit"))
