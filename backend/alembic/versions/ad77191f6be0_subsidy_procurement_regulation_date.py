"""Дата утверждения Положения о закупках — новая колонка subsidies.procurement_regulation_date

Карточка субсидии (поле рядом с «Дата документа-основания», owner задача
20.10.2026) + переменная шаблона документов {{procurement_regulation_date}}.

Идемпотентно (ADD COLUMN IF NOT EXISTS) — проект гоняет upgrade head при
старте контейнера, конфликт DDL иначе даёт 502.

Revision ID: ad77191f6be0
Revises: w6x7y8z9a0b1
Create Date: 2026-10-20 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'ad77191f6be0'
down_revision = 'w6x7y8z9a0b1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE subsidies ADD COLUMN IF NOT EXISTS procurement_regulation_date DATE"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE subsidies DROP COLUMN IF EXISTS procurement_regulation_date"
    ))
