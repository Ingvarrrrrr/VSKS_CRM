"""Уточняющая форма конкурентной процедуры закупки (competitive_form)

Владелец (2026-08-29/30): «"Запрос цен" — это вариант конкурсной процедуры,
так же как и Аукцион — он же редукцион, а также Конкурс. Необходимо
требовать заполнения способа закупки для формирования приказа, так же для
листа согласования наверное тоже надо».

purchase_method остаётся 'single' | 'competitive' | 'advance' — три способа
закупки. competitive_form НЕ отдельный способ закупки, а уточнение,
применимое ТОЛЬКО когда purchase_method == 'competitive':
  - 'price_request'  — Запрос цен
  - 'auction'         — Аукцион (редукцион)
  - 'tender'          — Конкурс

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  purchases:
    - competitive_form  VARCHAR(30)  NULL

Revision ID: u3v4w5x6y7z8
Revises: r1s2t3u4v5w6
Create Date: 2026-08-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = 'u3v4w5x6y7z8'
down_revision = 'r1s2t3u4v5w6'
branch_labels = None
depends_on = None


def _cols(table: str) -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    existing = _cols('purchases')

    if 'competitive_form' not in existing:
        op.add_column('purchases', sa.Column(
            'competitive_form', sa.String(30), nullable=True
        ))


def downgrade():
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS competitive_form'
    ))
