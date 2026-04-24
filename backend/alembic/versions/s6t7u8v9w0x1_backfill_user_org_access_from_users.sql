-- Phase 17.1-05: backfill user_org_access from users + user_organizations.
-- Idempotent — safe to re-run. Use this when alembic is unavailable on prod.
--
-- Revision: s6t7u8v9w0x1
-- Down-revision: r5s6t7u8v9w0

BEGIN;

-- Backfill 1: primary org from users.org_id
INSERT INTO user_org_access (user_id, org_id, role)
SELECT id, org_id, role
FROM users
WHERE org_id IS NOT NULL
ON CONFLICT (user_id, org_id) DO NOTHING;

-- Backfill 2: extra orgs from user_organizations (role mirrors user.role)
INSERT INTO user_org_access (user_id, org_id, role)
SELECT uo.user_id, uo.org_id, u.role
FROM user_organizations uo
JOIN users u ON u.id = uo.user_id
ON CONFLICT (user_id, org_id) DO NOTHING;

-- Stamp alembic head manually if you skipped `alembic upgrade`:
-- UPDATE alembic_version SET version_num = 's6t7u8v9w0x1';

COMMIT;
