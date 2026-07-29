"""Phase 28 T6/T7/T8: add 4 purchase fields + personal_account to contractors

Revision ID: t7u8v9w0x1y2
Revises: s6t7u8v9w0x1
Create Date: 2026-07-29 00:00:00.000000

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  purchases:
    - delivery_by_supplier  BOOLEAN NOT NULL DEFAULT true
    - has_stages            BOOLEAN NOT NULL DEFAULT false
    - procurement_protocol_number  VARCHAR(100)
    - procurement_order_number     VARCHAR(100)
    + 8 уже существующих полей Phase 28 (объявлены в модели, физически есть в БД — гвардим):
      contract_form, warranty_period_days, is_retroactive, acceptance_term_days,
      penalty_rate, contractor_ogrnip_date, repair_request_number, advance_amount
  contractors:
    - personal_account  VARCHAR(50)

downgrade(): DROP COLUMN IF EXISTS для всех 13 колонок.
"""

from alembic import op
import sqlalchemy as sa

revision = 't7u8v9w0x1y2'
down_revision = 's6t7u8v9w0x1'
branch_labels = None
depends_on = None


def _cols(table: str) -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    # ── purchases ──────────────────────────────────────────────────────────────
    existing_p = _cols('purchases')

    # 8 полей Phase 28, добавленных ручным DDL (уже физически есть в БД; гвардим)
    if 'contract_form' not in existing_p:
        op.add_column('purchases', sa.Column('contract_form', sa.String(50), nullable=True))

    if 'warranty_period_days' not in existing_p:
        op.add_column('purchases', sa.Column('warranty_period_days', sa.Integer(), nullable=True))

    if 'is_retroactive' not in existing_p:
        op.add_column('purchases', sa.Column(
            'is_retroactive', sa.Boolean(), nullable=False,
            server_default=sa.text('false')
        ))

    if 'acceptance_term_days' not in existing_p:
        op.add_column('purchases', sa.Column('acceptance_term_days', sa.Integer(), nullable=True))

    if 'penalty_rate' not in existing_p:
        op.add_column('purchases', sa.Column(
            'penalty_rate', sa.Numeric(5, 3), nullable=True
        ))

    if 'contractor_ogrnip_date' not in existing_p:
        op.add_column('purchases', sa.Column('contractor_ogrnip_date', sa.Date(), nullable=True))

    if 'repair_request_number' not in existing_p:
        op.add_column('purchases', sa.Column('repair_request_number', sa.String(50), nullable=True))

    if 'advance_amount' not in existing_p:
        op.add_column('purchases', sa.Column(
            'advance_amount', sa.Numeric(15, 2), nullable=True
        ))

    # 4 новых поля Phase 28 T6/T7/T8
    if 'delivery_by_supplier' not in existing_p:
        op.add_column('purchases', sa.Column(
            'delivery_by_supplier', sa.Boolean(), nullable=False,
            server_default=sa.text('true')
        ))

    if 'has_stages' not in existing_p:
        op.add_column('purchases', sa.Column(
            'has_stages', sa.Boolean(), nullable=False,
            server_default=sa.text('false')
        ))

    if 'procurement_protocol_number' not in existing_p:
        op.add_column('purchases', sa.Column(
            'procurement_protocol_number', sa.String(100), nullable=True
        ))

    if 'procurement_order_number' not in existing_p:
        op.add_column('purchases', sa.Column(
            'procurement_order_number', sa.String(100), nullable=True
        ))

    # ── contractors ────────────────────────────────────────────────────────────
    existing_c = _cols('contractors')

    if 'personal_account' not in existing_c:
        op.add_column('contractors', sa.Column(
            'personal_account', sa.String(50), nullable=True
        ))


def downgrade():
    # purchases — новые 4 поля
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS procurement_order_number'
    ))
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS procurement_protocol_number'
    ))
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS has_stages'
    ))
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS delivery_by_supplier'
    ))

    # purchases — 8 полей Phase 28 (ручной DDL)
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS advance_amount'
    ))
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS repair_request_number'
    ))
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS contractor_ogrnip_date'
    ))
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS penalty_rate'
    ))
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS acceptance_term_days'
    ))
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS is_retroactive'
    ))
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS warranty_period_days'
    ))
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS contract_form'
    ))

    # contractors
    op.execute(sa.text(
        'ALTER TABLE contractors DROP COLUMN IF EXISTS personal_account'
    ))
