"""Форма договора заявки — wishes.contract_form

Владелец (2026-09-15): «ВСЁ ДОЛЖНО БЫТЬ В ЗАЯВКЕ ТОЖЕ, ведь договора на
перевозку и питание могут быть не только рамочные, но и разовые». Спец-формы
позиций («Проживание»/«Перевозки автобусом»/«Питание», см.
app/services/item_forms.py) выводятся из contract_form — у Purchase это поле
уже есть (purchases.contract_form, миграция ранее), у Wish не было, поэтому
форма работала только после конвертации в закупку. Эта колонка даёт заявке
собственный contract_form (см. app/services/item_forms.py::item_form_for_wish),
который переносится в Purchase.contract_form при конвертации/распределении
(wish_convert.py, wish_distribution.py) — если у закупки форма ещё не задана.

Идемпотентно (ADD COLUMN IF NOT EXISTS) — проект гоняет upgrade head при
старте контейнера, конфликт DDL иначе валит бэкенд в 502.

Revision ID: a4c6e8g0i2k4
Revises: c2d4e6f8a0b2
Create Date: 2026-09-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a4c6e8g0i2k4'
down_revision = 'c2d4e6f8a0b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE wishes ADD COLUMN IF NOT EXISTS contract_form VARCHAR(50)"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE wishes DROP COLUMN IF EXISTS contract_form"
    ))
