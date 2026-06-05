"""wish_items.item_type расширить до VARCHAR(200)

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-05 18:00:00.000000

Контекст: фронт кладёт в item_type не «товар/услуга/работа», а описательный тип
позиции («Тренажер для тампонады» = 22 симв.). Колонка была VARCHAR(20) →
StringDataRightTruncation → INTERNAL_ERROR при сохранении заявки. Расширяем.

ОДИН statement на op.execute (asyncpg: prepared statement не принимает несколько
команд сразу).
"""
from alembic import op

revision = 'f3a4b5c6d7e8'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE wish_items ALTER COLUMN item_type TYPE VARCHAR(200);")


def downgrade() -> None:
    op.execute("ALTER TABLE wish_items ALTER COLUMN item_type TYPE VARCHAR(20);")
