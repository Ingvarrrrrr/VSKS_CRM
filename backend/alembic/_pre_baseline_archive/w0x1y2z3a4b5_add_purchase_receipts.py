"""phase21 add purchase_receipts table

Revision ID: w0x1y2z3a4b5
Revises: v9w0x1y2z3a4
Create Date: 2026-04-23

Phase 21.01 — multi-receipts on Advance Report.
Stores fiscal data of receipts attached to a purchase: from ФНС mobile-app
JSON share, from QR scan, or manual entry. Items extracted from JSON are
created as regular PurchaseItem rows (separate from this table).

Idempotent: uses CREATE TABLE / INDEX / CONSTRAINT IF NOT EXISTS so the
migration is safe to re-run.
"""
from alembic import op
import sqlalchemy as sa


revision = 'w0x1y2z3a4b5'
down_revision = 'v9w0x1y2z3a4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    connection.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS purchase_receipts (
          id SERIAL PRIMARY KEY,
          purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
          fiscal_drive_number VARCHAR(64),
          fiscal_document_number INTEGER,
          fiscal_sign VARCHAR(32),
          kkt_reg_id VARCHAR(64),
          receipt_datetime TIMESTAMP,
          total_sum NUMERIC(15,2),
          cash_sum NUMERIC(15,2),
          ecash_sum NUMERIC(15,2),
          prepaid_sum NUMERIC(15,2),
          nds_sum NUMERIC(15,2),
          seller_name VARCHAR(500),
          seller_inn VARCHAR(20),
          retail_place VARCHAR(500),
          retail_place_address VARCHAR(1000),
          operator VARCHAR(200),
          operator_inn VARCHAR(20),
          taxation_type INTEGER,
          source VARCHAR(20),
          raw_json JSONB,
          created_at TIMESTAMP DEFAULT NOW()
        )
    """))

    connection.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_purchase_receipts_purchase_id
          ON purchase_receipts(purchase_id)
    """))

    # UNIQUE on (fn, fd, fp) — guarded with DO block for idempotency
    connection.execute(sa.text("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'uq_receipt_fiscal'
          ) THEN
            ALTER TABLE purchase_receipts
              ADD CONSTRAINT uq_receipt_fiscal
              UNIQUE (fiscal_drive_number, fiscal_document_number, fiscal_sign);
          END IF;
        END$$;
    """))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("DROP TABLE IF EXISTS purchase_receipts CASCADE"))
