"""update purchases wish status to work_in_progress

Перевод всех закупок со статуса 'plan_schedule' в статус 'work_in_progress'
(«Ведётся работа»), так как любая реальная закупка проходит стадию заявки
и после согласования по ней ведётся работа. План закупок — это плановые позиции
дерева ФЭО (FeoPlannedItem).

Revision ID: a8c0e2f4b6d8
Revises: f7b8c9d0e1f2
Create Date: 2026-11-06 09:45:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "a8c0e2f4b6d8"
down_revision = "f7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text("""
        UPDATE purchases
        SET status = 'work_in_progress'
        WHERE status IN ('plan_schedule', 'planned')
    """))


def downgrade() -> None:
    pass
