"""Причина остановки закупки — purchases.stopped_reason

Владелец (2026-09-15): «Кнопка «Остановить закупку» — надо поставить», и во
вкладке «Закупки», и внутри самой закупки, плюс обратная операция
(возобновить). У Purchase уже есть stopped_at/stopped_by/stopped_wish_id
(миграция ранее, каскад из POST /api/wishes/{id}/stop) — но не было поля под
причину остановки, хотя у Wish.stopped_reason такое поле уже есть
(app/models/wish.py). Теперь остановить можно и саму закупку напрямую
(POST /api/purchases/{id}/stop, app/routers/purchase_stop.py), причина нужна
для баннера на карточке/в списке — тот же смысл поля, что и у заявки.

Идемпотентно (ADD COLUMN IF NOT EXISTS) — проект гоняет upgrade head при
старте контейнера, конфликт DDL иначе валит бэкенд в 502.

Revision ID: b6d8f0h2j4l6
Revises: a4c6e8g0i2k4
Create Date: 2026-09-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b6d8f0h2j4l6'
down_revision = 'a4c6e8g0i2k4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS stopped_reason TEXT"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE purchases DROP COLUMN IF EXISTS stopped_reason"
    ))
