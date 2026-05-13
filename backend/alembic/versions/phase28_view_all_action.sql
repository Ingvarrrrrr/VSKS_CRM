-- Phase 28: добавить action 'documents.view_all_in_org' + role defaults.
-- Idempotent: safe to re-run.
--
-- Это action управляет "галочкой видеть все документы в организации".
-- Когда у юзера эффективный action содержит этот ключ — backend
-- (app/auth/visibility.py:get_view_all_org_ids) добавляет org-wide ветку
-- в visibility clause для всех документов.
--
-- Apply on prod:
--   docker cp backend/alembic/versions/phase28_view_all_action.sql vsks-crm-db-1:/tmp/
--   docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -f /tmp/phase28_view_all_action.sql

-- 1) New action ----------------------------------------------------------
INSERT INTO permission_actions (action_key, description)
VALUES ('documents.view_all_in_org',
        'Видеть все документы организации без фильтра по ответственному исполнителю')
ON CONFLICT (action_key) DO NOTHING;

-- 2) Role defaults -------------------------------------------------------
INSERT INTO role_permissions (role_name, key, granted) VALUES
  ('superadmin',     'documents.view_all_in_org', TRUE),
  ('account_owner',  'documents.view_all_in_org', TRUE),
  ('admin',          'documents.view_all_in_org', TRUE),
  ('org_admin',      'documents.view_all_in_org', TRUE),
  ('manager',        'documents.view_all_in_org', FALSE),
  ('employee',       'documents.view_all_in_org', FALSE)
ON CONFLICT (role_name, key) DO NOTHING;

-- 3) Verification --------------------------------------------------------
SELECT 'permission_actions' AS table_name, COUNT(*) AS rows_with_key
FROM permission_actions WHERE action_key = 'documents.view_all_in_org'
UNION ALL
SELECT 'role_permissions', COUNT(*)
FROM role_permissions WHERE key = 'documents.view_all_in_org';
-- Expected: permission_actions=1, role_permissions=6
