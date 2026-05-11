-- Phase 25: seed permission action report_config.edit
-- Idempotent: safe to re-run.

INSERT INTO permission_actions (action_key, description)
VALUES ('report_config.edit', 'Создание/изменение/удаление шаблонов реестров, сводных, дашбордов в своей организации')
ON CONFLICT (action_key) DO NOTHING;

-- Granted to admin + org_admin by default
INSERT INTO role_permissions (role_name, key, granted)
VALUES
    ('superadmin',   'report_config.edit', true),
    ('account_owner','report_config.edit', true),
    ('admin',        'report_config.edit', true),
    ('org_admin',    'report_config.edit', true)
ON CONFLICT (role_name, key) DO UPDATE SET granted = true;
