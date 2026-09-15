"""Бюджет субсидии необязателен — subsidies.budget DROP NOT NULL

Владелец (2026-09-15): «Почему в поле „Бюджет" нельзя поставить пусто — „Ещё
не определено"». Subsidy.budget был NOT NULL float — заставлял ставить
0/произвольное число сразу при создании субсидии, хотя бюджет часто
согласовывается позже. NULL теперь = «бюджет ещё не определён»;
app.services.subsidy_budget.effective_subsidy_budget уже трактует NULL так
же, как 0 (float(manual_budget or 0)) — расчёты по дереву ФЭО не ломаются.

Идемпотентно — DROP NOT NULL на уже nullable-колонке в Postgres не ошибка
(проект гоняет upgrade head при старте контейнера, конфликт DDL иначе валит
бэкенд в 502).

Revision ID: c9e1g3i5k7m9
Revises: b6d8f0h2j4l6
Create Date: 2026-09-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9e1g3i5k7m9'
down_revision = 'b6d8f0h2j4l6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE subsidies ALTER COLUMN budget DROP NOT NULL"
    ))


def downgrade() -> None:
    # Backfill NULL → 0 первым, иначе SET NOT NULL упадёт на существующих
    # строках с уже очищенным бюджетом.
    op.execute(sa.text(
        "UPDATE subsidies SET budget = 0 WHERE budget IS NULL"
    ))
    op.execute(sa.text(
        "ALTER TABLE subsidies ALTER COLUMN budget SET NOT NULL"
    ))
