"""item-forms-accommodation-transport.md: extra_attrs JSONB на позициях

Хранилище полей спец-формы позиции («Проживание»/«Перевозки автобусом», см.
app/services/item_forms.py::ITEM_FORMS) — на purchase_items, wish_items и
contract_items (заявка может завести значения ДО конвертации; договор —
копия позиции закупки, «скопировать из заявки»/приёмка не должны их терять).

Никакого backfill — server_default покрывает уже существующие строки, форма
позиции выводится из purchase.contract_form (см. item_form_for_purchase),
а не хранится на самой позиции.

Идемпотентна (ADD COLUMN IF NOT EXISTS, тот же приём, что и в
a2b4c6d8e0f2_vehicle_plate_optional_passes_branding_tires.py).

Revision ID: c5e7g9i1k3m5
Revises: b4d6f8h0j2l4
Create Date: 2026-09-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c5e7g9i1k3m5"
down_revision = "b4d6f8h0j2l4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS extra_attrs JSONB NOT NULL DEFAULT '{}'::jsonb"
    ))
    op.execute(sa.text(
        "ALTER TABLE wish_items ADD COLUMN IF NOT EXISTS extra_attrs JSONB NOT NULL DEFAULT '{}'::jsonb"
    ))
    op.execute(sa.text(
        "ALTER TABLE contract_items ADD COLUMN IF NOT EXISTS extra_attrs JSONB NOT NULL DEFAULT '{}'::jsonb"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE contract_items DROP COLUMN IF EXISTS extra_attrs"))
    op.execute(sa.text("ALTER TABLE wish_items DROP COLUMN IF EXISTS extra_attrs"))
    op.execute(sa.text("ALTER TABLE purchase_items DROP COLUMN IF EXISTS extra_attrs"))
