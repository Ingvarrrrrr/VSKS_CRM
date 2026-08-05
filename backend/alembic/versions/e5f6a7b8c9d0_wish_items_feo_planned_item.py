"""wish_items: link to feo_planned_items (avoid duplicating plan-graph rows)

Revision ID: e5f6a7b8c9d0
Revises: w1x2y3z4a5b6
Create Date: 2026-08-04 00:00:00.000000

Заявка раньше умела указывать только категорию ФЭО (feo_category_id) —
согласованная заявка при конвертации создавала НОВУЮ строку план-графика
вместо расходования уже запланированной, план задваивался. У purchase_items
для этого уже есть feo_planned_item_id (см. backend/app/models/purchase_item.py) —
заводим парное поле у wish_items, чтобы связь можно было выбрать ещё на
этапе заявки и пробросить её при согласовании в PurchaseItem.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  wish_items:
    - feo_planned_item_id INTEGER NULL REFERENCES feo_planned_items(id) ON DELETE SET NULL
    - индекс ix_wish_items_feo_planned_item_id

downgrade(): DROP INDEX IF EXISTS + DROP COLUMN IF EXISTS.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'w1x2y3z4a5b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE wish_items ADD COLUMN IF NOT EXISTS feo_planned_item_id INTEGER "
        "REFERENCES feo_planned_items(id) ON DELETE SET NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_wish_items_feo_planned_item_id "
        "ON wish_items (feo_planned_item_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_wish_items_feo_planned_item_id"))
    op.execute(sa.text("ALTER TABLE wish_items DROP COLUMN IF EXISTS feo_planned_item_id"))
