-- Phase 18: seed permission tab 'staff_directory' + grant for all 5 roles
-- Idempotent: можно запускать многократно
-- Apply on prod: docker cp backend/alembic/versions/staff_directory_seed.sql vsks-crm-db-1:/tmp/ && docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -f /tmp/staff_directory_seed.sql

-- 1. Tab
INSERT INTO permission_tabs (tab_key, title)
VALUES ('staff_directory', 'Справочник сотрудников')
ON CONFLICT (tab_key) DO NOTHING;

-- 2. Role permissions (granted=true для всех 5 ролей: superadmin, admin, org_admin, manager, employee)
INSERT INTO role_permissions (role_name, key, granted)
SELECT r.role_name, 'staff_directory', TRUE
FROM (VALUES ('superadmin'), ('admin'), ('org_admin'), ('manager'), ('employee')) AS r(role_name)
ON CONFLICT (role_name, key) DO UPDATE SET granted = TRUE;
