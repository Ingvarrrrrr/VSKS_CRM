-- Phase 17.1-03 — link Organization -> Contractor via FK
-- Idempotent. Safe to re-run. For manual prod application via psql.
--
-- Usage:
--   docker cp r5s6t7u8v9w0_link_org_to_contractor.sql vsks-crm-db-1:/tmp/
--   docker exec -i vsks-crm-db-1 psql -U vsks -d vsks_crm -f /tmp/r5s6t7u8v9w0_link_org_to_contractor.sql

BEGIN;

-- Step A — add column if missing
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS contractor_id INTEGER
    REFERENCES contractors(id) ON DELETE SET NULL;

-- Step A.1 — index
CREATE INDEX IF NOT EXISTS ix_organizations_contractor_id
    ON organizations(contractor_id);

-- Step B — backfill by INN match (only rows where contractor_id is still NULL)
UPDATE organizations o
SET contractor_id = c.id
FROM contractors c
WHERE o.contractor_id IS NULL
  AND o.inn IS NOT NULL
  AND o.inn <> ''
  AND c.inn = o.inn;

-- Sanity: how many orgs got linked
-- SELECT id, name, inn, contractor_id FROM organizations ORDER BY id;

COMMIT;
