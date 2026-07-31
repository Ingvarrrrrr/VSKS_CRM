"""wishes/purchases: feo_per_item flag + wishes.vat_mode + wish_items.vat_rate

Revision ID: w1x2y3z4a5b6
Revises: t7u8v9w0x1y2
Create Date: 2026-07-31 00:00:00.000000

Первый шаг хранения режима «своя категория ФЭО для каждого товара»
(сейчас вычисляется эвристикой на фронте отдельно для заявки и закупки —
и слетает при конвертации заявки в закупку) + подготовка НДС per-item
для заявок (у закупки уже есть Purchase.vat_mode / PurchaseItem.vat_rate).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  wishes:
    - feo_per_item  BOOLEAN NOT NULL DEFAULT false
    - vat_mode      VARCHAR(20) DEFAULT 'uniform'
  wish_items:
    - vat_rate      VARCHAR(20)
  purchases:
    - feo_per_item  BOOLEAN NOT NULL DEFAULT false

Backfill (в этой же upgrade(), после ADD COLUMN): помечает feo_per_item=true
там, где уже есть позиции с индивидуальной категорией ФЭО — чтобы существующие
записи не потеряли разбивку при первом открытии карточки после миграции.

downgrade(): DROP COLUMN IF EXISTS для всех 4 колонок.
"""
from alembic import op
import sqlalchemy as sa

revision = 'w1x2y3z4a5b6'
down_revision = 't7u8v9w0x1y2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE wishes ADD COLUMN IF NOT EXISTS feo_per_item BOOLEAN NOT NULL DEFAULT false"
    ))
    op.execute(sa.text(
        "ALTER TABLE wishes ADD COLUMN IF NOT EXISTS vat_mode VARCHAR(20) DEFAULT 'uniform'"
    ))
    op.execute(sa.text(
        "ALTER TABLE wish_items ADD COLUMN IF NOT EXISTS vat_rate VARCHAR(20)"
    ))
    op.execute(sa.text(
        "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS feo_per_item BOOLEAN NOT NULL DEFAULT false"
    ))

    # Backfill: существующие заявки/закупки с уже расставленными per-item
    # категориями ФЭО помечаем как feo_per_item=true, чтобы не потерять
    # разбивку при первом открытии карточки.
    op.execute(sa.text(
        "UPDATE wishes SET feo_per_item = true"
        " WHERE id IN (SELECT DISTINCT wish_id FROM wish_items WHERE feo_category_id IS NOT NULL)"
    ))
    op.execute(sa.text(
        "UPDATE purchases SET feo_per_item = true"
        " WHERE id IN (SELECT DISTINCT purchase_id FROM purchase_items WHERE feo_category_id IS NOT NULL)"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE purchases DROP COLUMN IF EXISTS feo_per_item"))
    op.execute(sa.text("ALTER TABLE wish_items DROP COLUMN IF EXISTS vat_rate"))
    op.execute(sa.text("ALTER TABLE wishes DROP COLUMN IF EXISTS vat_mode"))
    op.execute(sa.text("ALTER TABLE wishes DROP COLUMN IF EXISTS feo_per_item"))
