"""Юр. адрес контрагента по частям — contractors.address_*

Владелец (28.10.2026): адрес доставки договора уже редактируется "по частям"
(regions/city/street — purchases.delivery_*). Тот же подход для юр. адреса
организации/контрагента: carточка контрагента получает поля-части (почтовый
индекс/регион/район-городской округ/населённый пункт с типом/улица/дом/
корпус/офис), собранные в `contractors.address` (единственное поле, которое
читают переменные документов — не трогается, см. app/services/address_compose.py
и app/schemas/contracts.py::ContractorCreate).

Попутно нашёлся и исправлен баг разбора адреса из ЕГРЮЛ/DaData: «г.о.
Бердянск» (Запорожская обл.) разбиралось как «о.Бердянск» — отдельная правка
в app/services/documents/formatting.py / app/services/address_compose.py, эта
миграция только добавляет колонки под part-поля.

Идемпотентно (ADD COLUMN IF NOT EXISTS) — проект гоняет upgrade head при
старте контейнера, конфликт DDL иначе даёт 502.

Линейно после a1c3e5f7b9d1 (purchases.fabrikant_no_nmcd), единственного head.

Revision ID: b4c6d8e0f2a4
Revises: a1c3e5f7b9d1
Create Date: 2026-10-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b4c6d8e0f2a4'
down_revision = 'a1c3e5f7b9d1'
branch_labels = None
depends_on = None

_COLUMNS = (
    ("address_postal_code", "VARCHAR(10)"),
    ("address_region", "VARCHAR(200)"),
    ("address_district", "VARCHAR(300)"),
    ("address_settlement_type", "VARCHAR(20)"),
    ("address_settlement", "VARCHAR(300)"),
    ("address_street", "VARCHAR(300)"),
    ("address_house", "VARCHAR(50)"),
    ("address_building", "VARCHAR(50)"),
    ("address_office", "VARCHAR(50)"),
)


def upgrade() -> None:
    for col, coltype in _COLUMNS:
        op.execute(sa.text(
            f"ALTER TABLE contractors ADD COLUMN IF NOT EXISTS {col} {coltype}"
        ))


def downgrade() -> None:
    for col, _ in _COLUMNS:
        op.execute(sa.text(
            f"ALTER TABLE contractors DROP COLUMN IF EXISTS {col}"
        ))
