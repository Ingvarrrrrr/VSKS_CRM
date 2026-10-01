"""«Проживание и питание»: item_form на СТРОКЕ (не на всю закупку/заявку)

Владелец, решение по задаче: новый contract_form 'services_accommodation_food'
— договор, где в каждой строке отдельно арендуются номера («Проживание»,
item_form=accommodation) и отдельно оплачивается питание («Питание»,
item_form=food). У остальных спец-форм (services_food/services_accommodation/
services_transport) форма одна на весь договор (Purchase.contract_form →
app/services/item_forms.py::CONTRACT_FORM_TO_ITEM_FORM), но здесь ОДНА закупка
может содержать и строки проживания, и строки питания одновременно — форму
обязана хранить сама строка, а не выводиться из шапки (Lessons.md:
«выбранное на предыдущем этапе не меняется само» — колонка, не эвристика).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  purchase_items, wish_items, contract_items:
    - item_form  VARCHAR(30) NULL

Downgrade — DROP COLUMN IF EXISTS (тоже идемпотентно).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'w7x8y9z0a1b2'
down_revision = 'u1v2w3x4y5z6'
branch_labels = None
depends_on = None

_TABLES = ("purchase_items", "wish_items", "contract_items")


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    for table in _TABLES:
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        if "item_form" not in existing_cols:
            op.add_column(table, sa.Column("item_form", sa.String(length=30), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    for table in _TABLES:
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        if "item_form" in existing_cols:
            op.drop_column(table, "item_form")
