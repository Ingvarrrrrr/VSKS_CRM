"""phase22 bank_statement_imports + bank_payments tables

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2026-04-27

Phase 22.01 — import of bank/treasury Excel statements.
BankStatementImport tracks each import run; BankPayment stores one normalised
row per statement line.  payments table gains bank_payment_id + matched_confirmed
for the confirm-match workflow.

Idempotent: CREATE TABLE / INDEX IF NOT EXISTS + DO $$ block for UNIQUE.
"""
from alembic import op
import sqlalchemy as sa


revision = 'y2z3a4b5c6d7'
down_revision = 'x1y2z3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    connection.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS bank_statement_imports (
            id SERIAL PRIMARY KEY,
            uploaded_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            file_name VARCHAR(500),
            sheet_name VARCHAR(200),
            rows_total INTEGER DEFAULT 0,
            rows_imported INTEGER DEFAULT 0,
            rows_skipped INTEGER DEFAULT 0,
            rows_matched INTEGER DEFAULT 0,
            rows_unmatched INTEGER DEFAULT 0,
            rows_dup INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'processing',
            error_message TEXT
        )
    """))

    connection.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS bank_payments (
            id SERIAL PRIMARY KEY,
            import_id INTEGER REFERENCES bank_statement_imports(id) ON DELETE CASCADE,
            payment_number VARCHAR(100),
            payment_date DATE,
            execution_datetime TIMESTAMP,
            status VARCHAR(100),
            amount NUMERIC(15,2),
            payer_inn VARCHAR(20),
            payer_kpp VARCHAR(20),
            payer_name VARCHAR(500),
            payer_account VARCHAR(50),
            payee_inn VARCHAR(20),
            payee_kpp VARCHAR(20),
            payee_name VARCHAR(500),
            payee_account VARCHAR(50),
            payee_bik VARCHAR(20),
            payee_bank VARCHAR(500),
            purpose_text TEXT,
            parsed_contract_number VARCHAR(200),
            parsed_contract_date DATE,
            parsed_kbk VARCHAR(50),
            raw_json JSONB DEFAULT '{}'::jsonb,
            matched_contractor_id INTEGER REFERENCES contractors(id) ON DELETE SET NULL,
            matched_contract_id INTEGER REFERENCES contracts(id) ON DELETE SET NULL,
            matched_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
            source_row_hash VARCHAR(64),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """))

    connection.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_bank_payment_source_row_hash
            ON bank_payments(source_row_hash)
    """))

    connection.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_bank_payment_payee_inn
            ON bank_payments(payee_inn)
    """))

    connection.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_bank_payment_contract_number
            ON bank_payments(parsed_contract_number)
    """))

    connection.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_bank_payment_matched
            ON bank_payments(matched_confirmed)
    """))

    connection.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_bank_payment_natural'
            ) THEN
                ALTER TABLE bank_payments
                    ADD CONSTRAINT uq_bank_payment_natural
                    UNIQUE (payment_number, payment_date, payer_inn, amount, parsed_contract_number);
            END IF;
        END$$;
    """))

    connection.execute(sa.text("""
        ALTER TABLE payments
            ADD COLUMN IF NOT EXISTS bank_payment_id INTEGER
                REFERENCES bank_payments(id) ON DELETE SET NULL
    """))

    connection.execute(sa.text("""
        ALTER TABLE payments
            ADD COLUMN IF NOT EXISTS matched_confirmed BOOLEAN NOT NULL DEFAULT FALSE
    """))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text(
        "ALTER TABLE payments DROP COLUMN IF EXISTS matched_confirmed"
    ))
    connection.execute(sa.text(
        "ALTER TABLE payments DROP COLUMN IF EXISTS bank_payment_id"
    ))
    connection.execute(sa.text(
        "DROP TABLE IF EXISTS bank_payments CASCADE"
    ))
    connection.execute(sa.text(
        "DROP TABLE IF EXISTS bank_statement_imports CASCADE"
    ))
