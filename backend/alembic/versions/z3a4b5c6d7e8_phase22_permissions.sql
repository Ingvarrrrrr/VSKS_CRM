-- Phase 22.04 permission seed — ручное применение на проде
-- Idempotent: все INSERT используют ON CONFLICT DO NOTHING

-- 1. Tab
INSERT INTO permission_tabs (tab_key, title)
VALUES ('payment_registry', 'Реестр платежей')
ON CONFLICT (tab_key) DO NOTHING;

-- 2. Actions
INSERT INTO permission_actions (action_key, description)
VALUES ('payment.import',  'Импорт банковских выписок')
ON CONFLICT (action_key) DO NOTHING;

INSERT INTO permission_actions (action_key, description)
VALUES ('payment.confirm', 'Подтверждение матча платежа')
ON CONFLICT (action_key) DO NOTHING;

INSERT INTO permission_actions (action_key, description)
VALUES ('payment.unbind',  'Откат подтверждения платежа')
ON CONFLICT (action_key) DO NOTHING;

-- 3. Role permissions — full access: superadmin, account_owner, admin, manager
INSERT INTO role_permissions (role_name, key, granted)
SELECT r.role, k.key, TRUE
FROM (VALUES
    ('superadmin'), ('account_owner'), ('admin'), ('manager')
) AS r(role)
CROSS JOIN (VALUES
    ('payment_registry'), ('payment.import'), ('payment.confirm'), ('payment.unbind')
) AS k(key)
ON CONFLICT (role_name, key) DO NOTHING;

-- 4. org_admin — tab + confirm only
INSERT INTO role_permissions (role_name, key, granted)
SELECT 'org_admin', k.key, TRUE
FROM (VALUES
    ('payment_registry'), ('payment.confirm')
) AS k(key)
ON CONFLICT (role_name, key) DO NOTHING;
