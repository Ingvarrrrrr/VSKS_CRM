"""wish_items.tz_description / purchase_items.tz_description — своё ТЗ
(характеристики) позиции заявки/закупки (владелец, 14.10.2026, план
item-tz-description.md, Этап А): «Прил4 ТЗ (Видео).docx» — при импорте ТЗ
характеристики из файла теряются; каталог товаров общий для всего
приложения (Product, org_id NULL) — плохое ТЗ одного не должно испортить
всем. Действующее ТЗ позиции = tz_description (если непустое), иначе
product.description — см. app/services/item_tz.py::effective_item_tz.

Оба поля NULL, TEXT. Идемпотентно: ADD COLUMN IF NOT EXISTS.

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-10-14
"""
from alembic import op
from sqlalchemy import text

revision = 'l2m3n4o5p6q7'
down_revision = 'k1l2m3n4o5p6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(
        "ALTER TABLE wish_items ADD COLUMN IF NOT EXISTS tz_description TEXT"
    ))
    bind.execute(text(
        "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS tz_description TEXT"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("ALTER TABLE purchase_items DROP COLUMN IF EXISTS tz_description"))
    bind.execute(text("ALTER TABLE wish_items DROP COLUMN IF EXISTS tz_description"))
