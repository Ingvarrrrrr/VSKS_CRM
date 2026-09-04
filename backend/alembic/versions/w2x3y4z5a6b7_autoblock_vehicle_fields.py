"""Автоблок: полный реестр полей карточки ТС (35 новых колонок vehicles)

Источник требований: лист «26.05.2026» файла Голичкова (71 колонка, реестр
транспорта). Организация вправе скрыть ненужные поля (см. app/services/
vehicle_fields.py + app/routers/vehicle_fields.py) — конфигурация скрытия
переиспользует существующую таблицу org_section_config (без новой таблицы).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS) в vehicles:
  Идентификация: body_type, pts_category
  Документы:     insurance_company, insurance_policy_number,
                 pts_kind, sts_issued_at,
                 tech_inspection_status, tech_inspection_last_date
  Собственность: ownership_basis, ownership_doc_number, ownership_doc_date,
                 owner_since
  Эксплуатация:  location_city, location_address, responsible_name
  Пропуска:      pass_zo/_until, pass_ho/_until, pass_dnr/_until,
                 pass_lnr/_until, pass_moscow/_until (10 колонок)
  Оснащение:     has_spare_tires, tires_condition, has_mirrors,
                 first_aid_kit_until, extinguisher_check_date,
                 tracker_paid_until, has_tachograph, tachograph_check_date
  Состояние:     repair_required, tech_condition_info

Все колонки nullable. Даты — DATE, тексты — VARCHAR(N) согласно
AUTOBLOCK_FIELDS_SPEC.md §1, tech_condition_info — TEXT.

Revision ID: w2x3y4z5a6b7
Revises: p9r2t5v8x1z4
Create Date: 2026-08-31 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'w2x3y4z5a6b7'
down_revision = 'p9r2t5v8x1z4'
branch_labels = None
depends_on = None

# (имя колонки, SQL-тип) — порядок соответствует AUTOBLOCK_FIELDS_SPEC.md §1
_NEW_COLUMNS = [
    ("body_type", "VARCHAR(50)"),
    ("pts_category", "VARCHAR(10)"),
    ("insurance_company", "VARCHAR(150)"),
    ("insurance_policy_number", "VARCHAR(100)"),
    ("ownership_basis", "VARCHAR(200)"),
    ("ownership_doc_number", "VARCHAR(100)"),
    ("ownership_doc_date", "DATE"),
    ("owner_since", "DATE"),
    ("location_city", "VARCHAR(100)"),
    ("location_address", "VARCHAR(300)"),
    ("responsible_name", "VARCHAR(150)"),
    ("pts_kind", "VARCHAR(20)"),
    ("sts_issued_at", "DATE"),
    ("tech_inspection_status", "VARCHAR(100)"),
    ("tech_inspection_last_date", "DATE"),
    ("pass_zo", "VARCHAR(100)"),
    ("pass_zo_until", "DATE"),
    ("pass_ho", "VARCHAR(100)"),
    ("pass_ho_until", "DATE"),
    ("pass_dnr", "VARCHAR(100)"),
    ("pass_dnr_until", "DATE"),
    ("pass_lnr", "VARCHAR(100)"),
    ("pass_lnr_until", "DATE"),
    ("pass_moscow", "VARCHAR(100)"),
    ("pass_moscow_until", "DATE"),
    ("has_spare_tires", "BOOLEAN"),
    ("tires_condition", "VARCHAR(100)"),
    ("has_mirrors", "BOOLEAN"),
    ("first_aid_kit_until", "DATE"),
    ("extinguisher_check_date", "DATE"),
    ("tracker_paid_until", "DATE"),
    ("has_tachograph", "BOOLEAN"),
    ("tachograph_check_date", "DATE"),
    ("repair_required", "BOOLEAN"),
    ("tech_condition_info", "TEXT"),
]


def upgrade() -> None:
    for col_name, col_type in _NEW_COLUMNS:
        op.execute(sa.text(f"ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))


def downgrade() -> None:
    for col_name, _col_type in reversed(_NEW_COLUMNS):
        op.execute(sa.text(f"ALTER TABLE vehicles DROP COLUMN IF EXISTS {col_name}"))
