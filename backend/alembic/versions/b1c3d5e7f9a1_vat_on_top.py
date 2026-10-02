"""НДС «в цене» или «сверху» при вводе цены позиции (владелец, 02.10.2026,
план .planning/quick/2026-10-02-vat-on-top/PLAN.md).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS — ПРАВИЛО миграций,
check_schema/автодеплой может перегонять upgrade head повторно):
  - purchases.tz_vat_on_top, purchases.contract_vat_on_top — BOOLEAN NOT NULL
    DEFAULT false (раздельно для цены ТЗ и цены договора);
  - wishes.tz_vat_on_top — BOOLEAN NOT NULL DEFAULT false;
  - purchase_items.vat_on_top, contract_items.vat_on_top, wish_items.vat_on_top
    — BOOLEAN NULL (null = «как у закупки/заявки», см. app.services.item_amounts
    .effective_vat_on_top — действуют только в режиме vat_mode='per_item').

Revision ID: b1c3d5e7f9a1
Revises: x8y9z0a1b2c3
Create Date: 2026-10-02 00:00:00.000000

NOTE (02.10.2026): на момент создания этой миграции в versions/ уже было ДВЕ
головы — x8y9z0a1b2c3 (эта цепочка) и d3e5f7g9h1j3 (152-ФЗ: user_consents +
personal_data_requests, параллельная незакоммиченная работа другого
исполнителя). Эта миграция сознательно продолжает x8y9z0a1b2c3, не трогая
152-ФЗ ветку — слияние голов (alembic merge) оставлено тому, кто сведёт обе
работы воедино.
"""
from alembic import op

revision = 'b1c3d5e7f9a1'
down_revision = 'x8y9z0a1b2c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE purchases ADD COLUMN IF NOT EXISTS tz_vat_on_top BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE purchases ADD COLUMN IF NOT EXISTS contract_vat_on_top BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE wishes ADD COLUMN IF NOT EXISTS tz_vat_on_top BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS vat_on_top BOOLEAN")
    op.execute("ALTER TABLE contract_items ADD COLUMN IF NOT EXISTS vat_on_top BOOLEAN")
    op.execute("ALTER TABLE wish_items ADD COLUMN IF NOT EXISTS vat_on_top BOOLEAN")


def downgrade() -> None:
    op.execute("ALTER TABLE wish_items DROP COLUMN IF EXISTS vat_on_top")
    op.execute("ALTER TABLE contract_items DROP COLUMN IF EXISTS vat_on_top")
    op.execute("ALTER TABLE purchase_items DROP COLUMN IF EXISTS vat_on_top")
    op.execute("ALTER TABLE wishes DROP COLUMN IF EXISTS tz_vat_on_top")
    op.execute("ALTER TABLE purchases DROP COLUMN IF EXISTS contract_vat_on_top")
    op.execute("ALTER TABLE purchases DROP COLUMN IF EXISTS tz_vat_on_top")
