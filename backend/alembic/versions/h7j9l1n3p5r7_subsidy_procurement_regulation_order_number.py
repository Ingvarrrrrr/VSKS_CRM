"""Номер приказа об утверждении Положения о закупках — новая колонка
subsidies.procurement_regulation_order_number

Карточка субсидии (поле рядом с «Дата утверждения Положения о закупках»,
owner задача 22.10.2026) + переменная шаблона документов
{{procurement_regulation_order_number}}.

Идемпотентно (ADD COLUMN IF NOT EXISTS) — проект гоняет upgrade head при
старте контейнера, конфликт DDL иначе даёт 502.

Revision ID: h7j9l1n3p5r7
Revises: g6i8k0m2o4q6
Create Date: 2026-10-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'h7j9l1n3p5r7'
down_revision = 'f4h6j8l0n2p4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE subsidies ADD COLUMN IF NOT EXISTS procurement_regulation_order_number VARCHAR(100)"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE subsidies DROP COLUMN IF EXISTS procurement_regulation_order_number"
    ))
