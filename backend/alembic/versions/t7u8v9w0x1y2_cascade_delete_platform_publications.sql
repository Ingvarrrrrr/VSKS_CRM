-- Phase 17.1-07 hotfix: cascade delete platform_publications when the
-- parent purchase is removed. Idempotent — safe to re-run.
--
-- Revision: t7u8v9w0x1y2
-- Down-revision: s6t7u8v9w0x1
--
-- Context: DELETE /api/purchases/{id} fails on prod with
--   NotNullViolationError: null value in column "purchase_id" of relation
--   "platform_publications" violates not-null constraint
-- SQLAlchemy tried to UPDATE ... SET purchase_id=NULL because the backref
-- lacked passive_deletes. The app model was fixed (passive_deletes=True +
-- cascade="all, delete-orphan"), but the DB-level FK on prod was still
-- created without ON DELETE CASCADE. This script recreates the FK with
-- CASCADE so the database itself handles child-row removal.

BEGIN;

-- 1. Drop existing FK (name can vary per environment)
DO $$
DECLARE
    fk_name text;
BEGIN
    SELECT conname INTO fk_name
    FROM pg_constraint
    WHERE conrelid = 'platform_publications'::regclass
      AND contype = 'f'
      AND array_to_string(conkey, ',') = (
        SELECT array_to_string(array_agg(attnum ORDER BY attnum), ',')
        FROM pg_attribute
        WHERE attrelid = 'platform_publications'::regclass
          AND attname = 'purchase_id'
      );
    IF fk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE platform_publications DROP CONSTRAINT %I', fk_name);
    END IF;
END $$;

-- 2. Recreate FK with ON DELETE CASCADE
ALTER TABLE platform_publications
  ADD CONSTRAINT platform_publications_purchase_id_fkey
  FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE;

-- 3. Stamp alembic head manually if you applied SQL without running alembic:
-- UPDATE alembic_version SET version_num = 't7u8v9w0x1y2';

COMMIT;
