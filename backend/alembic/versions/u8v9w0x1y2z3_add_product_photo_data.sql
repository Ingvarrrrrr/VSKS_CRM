-- Phase 17.1-08: add bytea storage for product photos. Idempotent — safe to
-- re-run.
--
-- Revision: u8v9w0x1y2z3
-- Down-revision: t7u8v9w0x1y2
--
-- Context: /app/uploads/products volume is unreliable. Store photos directly
-- in the database so a single DB backup is enough to restore them.
-- `photo_url` stays untouched (it may still contain the external marketplace
-- URL used as source of truth for re-download).

BEGIN;

ALTER TABLE products ADD COLUMN IF NOT EXISTS photo_data BYTEA;
ALTER TABLE products ADD COLUMN IF NOT EXISTS photo_mime VARCHAR(50);
ALTER TABLE products ADD COLUMN IF NOT EXISTS photo_size INTEGER;

-- Stamp alembic head manually if you applied SQL without running alembic:
-- UPDATE alembic_version SET version_num = 'u8v9w0x1y2z3';

COMMIT;
