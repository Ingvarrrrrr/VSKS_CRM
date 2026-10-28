"""purchases.fabrikant_no_nmcd — «Без НМЦД» для Фабриканта как ЕДИНСТВЕННОЕ
хранимое состояние (владелец, 28.10.2026, ПРАВИЛО №6).

Повод: кнопка «Без НМЦД» раньше существовала только как эфемерный флаг
диалога ОТПРАВКИ пакета (PublishRequest.no_nmcd, app/schemas/marketplace.py →
app/routers/publications.py) — не сохранялась в БД. Нужна та же возможность
при простом СКАЧИВАНИИ пакета (без отправки), а диалог отправки должен
помнить прошлый выбор, а не сбрасываться на эвристику при каждом открытии.
Вместо второго состояния — одно поле на закупке, которое читают и пишут обе
точки входа (скачивание и отправка).

Idempotent: ADD COLUMN IF NOT EXISTS под inspector-guard, как соседние
миграции на purchases (см. d4e6f8a0b2c4_purchase_procurement_order_date.py).

Revision ID: a1c3e5f7b9d1
Revises: f5a7c9e1b3d5
Create Date: 2026-10-28 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'a1c3e5f7b9d1'
down_revision = 'f5a7c9e1b3d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'purchases' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('purchases')}
    if 'fabrikant_no_nmcd' not in cols:
        op.execute(sa.text(
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS fabrikant_no_nmcd "
            "BOOLEAN NOT NULL DEFAULT false"
        ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE purchases DROP COLUMN IF EXISTS fabrikant_no_nmcd"))
