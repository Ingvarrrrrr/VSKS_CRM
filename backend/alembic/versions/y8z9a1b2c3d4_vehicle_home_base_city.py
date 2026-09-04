"""Место постоянной приписки ТС — новая колонка vehicles.home_base_city

Распоряжение владельца: у машины два разных места — постоянная приписка (где
закреплена) и текущее нахождение (где физически сейчас, уже есть как
location_city/location_address, используется географией парка на карте).
Эта миграция добавляет только город постоянной приписки; парного поля под
адрес приписки (home_base_address) не добавляет — владелец просил именно
"место", без уточнения адреса (см. AUTOBLOCK_FIELDS_SPEC.md / TASKS.md
обоснование в отчёте задачи).

Подписи полей location_city/location_address переименованы в реестре
app/services/vehicle_fields.py на "Текущее место нахождения, город/адрес" —
без изменений схемы БД (это только label, не колонка).

Идемпотентно (ADD COLUMN IF NOT EXISTS) — проект гоняет upgrade head при
старте контейнера, конфликт DDL иначе даёт 502.

ИСПРАВЛЕНО (2026-09-02): revision w2x3y4z5a6b7 ("autoblock_vehicle_fields") —
не чужая работа, а часть этой же сессии (карточка ТС, реестр полей, импорт
реестра владельца), просто не была ещё закоммичена. Она больше не исключена
из докер-образа (backend/.dockerignore), поэтому эта миграция цепляется
штатно к w2x3y4z5a6b7, а не к p9r2t5v8x1z4 напрямую — цепочка теперь
p9r2t5v8x1z4 -> w2x3y4z5a6b7 -> y8z9a1b2c3d4, голова одна.

Revision ID: y8z9a1b2c3d4
Revises: w2x3y4z5a6b7
Create Date: 2026-09-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'y8z9a1b2c3d4'
down_revision = 'w2x3y4z5a6b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS home_base_city VARCHAR(100)"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE vehicles DROP COLUMN IF EXISTS home_base_city"
    ))
