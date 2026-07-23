"""purchases: migrate status confirmed → work_in_progress

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-07-23 00:00:00.000000
"""
from alembic import op
from sqlalchemy import text


revision = 'm7n8o9p0q1r2'
down_revision = 'l6m7n8o9p0q1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Статус «confirmed» упразднён — сливается с «work_in_progress».
    # Идемпотентен: повторный запуск ничего не меняет (WHERE = только confirmed).
    op.execute(text(
        "UPDATE purchases SET status = 'work_in_progress' WHERE status = 'confirmed'"
    ))


def downgrade() -> None:
    # Обратная миграция не поддерживается намеренно:
    # восстановить какие именно записи были confirmed невозможно.
    pass
