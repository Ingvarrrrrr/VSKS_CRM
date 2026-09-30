"""purchase_items.item_type varchar(20) -> varchar(200), как wish_items.item_type.

Повод (владелец, 30.09): согласование заявки №90 падало 500
(StringDataRightTruncationError) — в заявке «Тип» хранит вид товара до 200
символов («Клей-карандаш Комус 15 г»), а при распределении в закупку поле
позиции закупки было varchar(20).
"""
from alembic import op

revision = "d0g2i4k6m8o0"
down_revision = "c9f1h3j5l7n9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE purchase_items ALTER COLUMN item_type TYPE varchar(200)")


def downgrade() -> None:
    pass
