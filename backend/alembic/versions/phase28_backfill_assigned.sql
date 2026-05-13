-- Phase 28: backfill purchases.assigned_user_id where NULL.
-- Idempotent: safe to re-run.
--
-- Strategy (priority order):
--   1. user_id of purchase_event with event_type='created' (earliest)
--   2. first PurchaseMember.user_id with role='owner' or 'executor', then any
--   3. first user with role 'org_admin' in subsidy's org (via user_org_access)
-- Rows that remain NULL after all three passes are reported at the end —
-- those need manual triage via UI.
--
-- Apply on prod (READ before/after counts!):
--   docker cp backend/alembic/versions/phase28_backfill_assigned.sql vsks-crm-db-1:/tmp/
--   docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -f /tmp/phase28_backfill_assigned.sql

\echo ''
\echo '=== Before backfill ==='
SELECT COUNT(*) AS purchases_with_null_assigned
FROM purchases WHERE assigned_user_id IS NULL;

-- Pass 1: from purchase_events (event_type='created') ---------------------
WITH first_created AS (
    SELECT DISTINCT ON (purchase_id)
        purchase_id, user_id
    FROM purchase_events
    WHERE event_type = 'created' AND user_id IS NOT NULL
    ORDER BY purchase_id, created_at ASC
)
UPDATE purchases p
SET assigned_user_id = fc.user_id
FROM first_created fc
WHERE p.id = fc.purchase_id
  AND p.assigned_user_id IS NULL;

\echo ''
\echo '=== After pass 1 (purchase_events) ==='
SELECT COUNT(*) AS purchases_with_null_assigned
FROM purchases WHERE assigned_user_id IS NULL;

-- Pass 2: from purchase_members (owner > executor > any) ------------------
WITH first_member AS (
    SELECT DISTINCT ON (purchase_id)
        purchase_id, user_id
    FROM purchase_members
    ORDER BY purchase_id,
        CASE role
            WHEN 'owner'    THEN 1
            WHEN 'executor' THEN 2
            ELSE 3
        END,
        created_at ASC NULLS LAST,
        id ASC
)
UPDATE purchases p
SET assigned_user_id = fm.user_id
FROM first_member fm
WHERE p.id = fm.purchase_id
  AND p.assigned_user_id IS NULL;

\echo ''
\echo '=== After pass 2 (purchase_members) ==='
SELECT COUNT(*) AS purchases_with_null_assigned
FROM purchases WHERE assigned_user_id IS NULL;

-- Pass 3: org_admin of subsidy's org -------------------------------------
WITH org_admin_per_subsidy AS (
    SELECT DISTINCT ON (s.id)
        s.id AS subsidy_id, uoa.user_id
    FROM subsidies s
    JOIN user_org_access uoa ON uoa.org_id = s.org_id
    WHERE uoa.role IN ('org_admin', 'admin')
    ORDER BY s.id, uoa.id ASC
)
UPDATE purchases p
SET assigned_user_id = oa.user_id
FROM org_admin_per_subsidy oa
WHERE p.subsidy_id = oa.subsidy_id
  AND p.assigned_user_id IS NULL;

\echo ''
\echo '=== After pass 3 (org_admin fallback) ==='
SELECT COUNT(*) AS purchases_with_null_assigned
FROM purchases WHERE assigned_user_id IS NULL;

-- Unresolved report -------------------------------------------------------
\echo ''
\echo '=== Unresolved purchases (need manual triage) ==='
SELECT
    p.id,
    p.purchase_number,
    p.registry_number,
    LEFT(COALESCE(p.subject, p.item_name, ''), 60) AS subject_or_item,
    p.status,
    p.subsidy_id,
    s.name AS subsidy_name
FROM purchases p
LEFT JOIN subsidies s ON s.id = p.subsidy_id
WHERE p.assigned_user_id IS NULL
ORDER BY p.id;
