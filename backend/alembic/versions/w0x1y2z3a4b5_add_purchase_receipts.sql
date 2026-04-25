-- Phase 21.01 — purchase_receipts table (multi-receipts for Advance Report)
-- Idempotent: CREATE ... IF NOT EXISTS + DO block for unique constraint.

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
);

CREATE INDEX IF NOT EXISTS ix_purchase_receipts_purchase_id
  ON purchase_receipts(purchase_id);

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

-- Mark migration as applied (so alembic stamp matches).
INSERT INTO alembic_version (version_num) VALUES ('w0x1y2z3a4b5')
ON CONFLICT DO NOTHING;
