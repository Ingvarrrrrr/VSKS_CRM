"""baseline schema from prod

Revision ID: 77a79dee6f2f
Revises:
Create Date: 2026-06-02 08:28:44.071360

This is the adoption baseline for Alembic. Prior to this the schema was managed
by runtime-DDL (_ensure_* functions + create_all at startup); the old migration
chain was broken (3 heads + a duplicate revision id) and is archived under
alembic/_pre_baseline_archive/.

upgrade() builds the full current schema via Base.metadata.create_all (which
correctly orders/defers the circular FKs among contractors/organizations/users),
then adds three legacy tables that have no SQLAlchemy model. Existing databases
(local, prod) are NOT migrated through this — they are `alembic stamp`-ed to this
revision, so upgrade() only ever runs on a fresh DB (CI / new deployment).
"""
from alembic import op

from app.database import Base
from app.models import *  # noqa: F401,F403  (populate Base.metadata)

# revision identifiers, used by Alembic.
revision = '77a79dee6f2f'
down_revision = None
branch_labels = None
depends_on = None

# Legacy tables present in the DB via runtime-DDL but with no SQLAlchemy model.
# Excluded from autogenerate via include_object in env.py; created here so a
# fresh DB bootstrapped from this baseline matches prod (88 tables, not 85).
# Order matters: closing_documents has an FK to purchases (a model table, so it
# already exists after create_all); sequences/defaults/pkeys/indexes/FK follow.
_LEGACY_DDL = [
    "CREATE TABLE closing_documents (id integer NOT NULL, purchase_id integer NOT NULL, doc_type character varying(50) NOT NULL, doc_number character varying(100), doc_date date, amount numeric(15,2), note character varying(500), created_at timestamp with time zone DEFAULT now())",
    "CREATE SEQUENCE closing_documents_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE closing_documents_id_seq OWNED BY closing_documents.id",
    "ALTER TABLE ONLY closing_documents ALTER COLUMN id SET DEFAULT nextval('closing_documents_id_seq'::regclass)",
    "ALTER TABLE ONLY closing_documents ADD CONSTRAINT closing_documents_pkey PRIMARY KEY (id)",
    "CREATE INDEX ix_closing_documents_id ON closing_documents USING btree (id)",
    "CREATE INDEX ix_closing_documents_purchase_id ON closing_documents USING btree (purchase_id)",
    "ALTER TABLE ONLY closing_documents ADD CONSTRAINT closing_documents_purchase_id_fkey FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE",
    "CREATE TABLE expense_directions (id integer NOT NULL, name character varying(500), subsidy_id integer)",
    "CREATE SEQUENCE expense_directions_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE expense_directions_id_seq OWNED BY expense_directions.id",
    "ALTER TABLE ONLY expense_directions ALTER COLUMN id SET DEFAULT nextval('expense_directions_id_seq'::regclass)",
    "ALTER TABLE ONLY expense_directions ADD CONSTRAINT expense_directions_pkey PRIMARY KEY (id)",
    "CREATE TABLE idempotency_keys (key character varying(128) NOT NULL, method character varying(10) NOT NULL, path character varying(500) NOT NULL, status_code integer NOT NULL, response_body text, created_at timestamp with time zone DEFAULT now() NOT NULL, expires_at timestamp with time zone NOT NULL)",
    "ALTER TABLE ONLY idempotency_keys ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (key)",
    "CREATE INDEX ix_idempotency_keys_expires_at ON idempotency_keys USING btree (expires_at)",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    for stmt in _LEGACY_DDL:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS closing_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS expense_directions CASCADE")
    op.execute("DROP TABLE IF EXISTS idempotency_keys CASCADE")
    Base.metadata.drop_all(bind=op.get_bind())
