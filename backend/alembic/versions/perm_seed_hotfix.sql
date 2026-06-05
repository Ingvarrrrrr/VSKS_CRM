-- Hotfix 17.1-01: create missing permission tables + seed Phase 17 matrix
-- Idempotent: safe to re-run.

-- ------------------------------------------------------------------ --
-- Create missing tables (2 of 4 — the DDL for *_tabs and *_actions   --
-- was already created via SQLAlchemy create_all on prod).            --
-- ------------------------------------------------------------------ --

CREATE TABLE IF NOT EXISTS role_permissions (
  id SERIAL PRIMARY KEY,
  role_name VARCHAR(32) NOT NULL,
  key VARCHAR(64) NOT NULL,
  granted BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at TIMESTAMP DEFAULT NOW(),
  CONSTRAINT uq_role_perm UNIQUE (role_name, key)
);
CREATE INDEX IF NOT EXISTS ix_role_permissions_role_name ON role_permissions(role_name);
CREATE INDEX IF NOT EXISTS ix_role_permissions_key ON role_permissions(key);

CREATE TABLE IF NOT EXISTS user_org_permission_overrides (
  id SERIAL PRIMARY KEY,
  user_org_access_id INTEGER NOT NULL REFERENCES user_org_access(id) ON DELETE CASCADE,
  key VARCHAR(64) NOT NULL,
  granted BOOLEAN NOT NULL,
  updated_at TIMESTAMP DEFAULT NOW(),
  CONSTRAINT uq_uoa_override UNIQUE (user_org_access_id, key)
);
CREATE INDEX IF NOT EXISTS ix_user_org_permission_overrides_user_org_access_id ON user_org_permission_overrides(user_org_access_id);
CREATE INDEX IF NOT EXISTS ix_user_org_permission_overrides_key ON user_org_permission_overrides(key);

-- ------------------------------------------------------------------ --
-- Seed permission_tabs (23 rows)                                     --
-- ------------------------------------------------------------------ --
INSERT INTO permission_tabs (tab_key, title) VALUES
  ('dashboard', 'Дашборд'),
  ('dashboard.radar', 'Risk Radar'),
  ('my_tasks', 'Мои задачи и закупки'),
  ('wishes', 'Заявки'),
  ('subsidies', 'Субсидии'),
  ('purchases', 'Закупки'),
  ('contractors', 'Контрагенты'),
  ('contracts', 'Договоры'),
  ('products', 'Товары'),
  ('products.summary', 'Сводная по продукции'),
  ('feo_categories', 'Категории ФЭО'),
  ('commercial_requests', 'Запросы КП'),
  ('staff', 'Персонал'),
  ('reports', 'Отчёты'),
  ('plan', 'План-график'),
  ('system_incidents', 'Инциденты'),
  ('admin.organizations', 'Организации'),
  ('admin.billing', 'Биллинг'),
  ('service_notes', 'Служебные записки'),
  ('advance_reports', 'Авансовые отчёты'),
  ('admin.settings', 'Настройки'),
  ('chat', 'Чат'),
  ('admin.roles', 'Роли')
ON CONFLICT (tab_key) DO NOTHING;

-- ------------------------------------------------------------------ --
-- Seed permission_actions (7 rows)                                   --
-- ------------------------------------------------------------------ --
INSERT INTO permission_actions (action_key, description) VALUES
  ('purchase.transition_status', 'Перевод статуса закупки'),
  ('wish.approve', 'Одобрение заявки'),
  ('contract.delete', 'Удаление договора'),
  ('payment.register', 'Регистрация выплаты'),
  ('publication.create', 'Создание публикации'),
  ('subsidy.edit', 'Редактирование/удаление субсидии'),
  ('user.manage', 'Управление персоналом')
ON CONFLICT (action_key) DO NOTHING;

-- ------------------------------------------------------------------ --
-- Seed role_permissions from the hardcoded matrix                    --
--   ADMIN   = {superadmin, account_owner, admin, org_admin}          --
--   MANAGER = ADMIN + manager                                         --
--   ALL     = MANAGER + employee                                      --
-- ------------------------------------------------------------------ --
WITH matrix(key, role_name) AS (VALUES
  -- Tabs
  ('dashboard',           'superadmin'),   ('dashboard',           'account_owner'), ('dashboard',           'admin'), ('dashboard',           'org_admin'), ('dashboard',           'manager'),
  ('dashboard.radar',     'superadmin'),   ('dashboard.radar',     'account_owner'), ('dashboard.radar',     'admin'), ('dashboard.radar',     'org_admin'), ('dashboard.radar',     'manager'),
  ('my_tasks',            'superadmin'),   ('my_tasks',            'account_owner'), ('my_tasks',            'admin'), ('my_tasks',            'org_admin'), ('my_tasks',            'manager'), ('my_tasks',            'employee'),
  ('wishes',              'superadmin'),   ('wishes',              'account_owner'), ('wishes',              'admin'), ('wishes',              'org_admin'), ('wishes',              'manager'), ('wishes',              'employee'),
  ('subsidies',           'superadmin'),   ('subsidies',           'account_owner'), ('subsidies',           'admin'), ('subsidies',           'org_admin'),
  ('purchases',           'superadmin'),   ('purchases',           'account_owner'), ('purchases',           'admin'), ('purchases',           'org_admin'), ('purchases',           'manager'), ('purchases',           'employee'),
  ('contractors',         'superadmin'),   ('contractors',         'account_owner'), ('contractors',         'admin'), ('contractors',         'org_admin'), ('contractors',         'manager'), ('contractors',         'employee'),
  ('contracts',           'superadmin'),   ('contracts',           'account_owner'), ('contracts',           'admin'), ('contracts',           'org_admin'), ('contracts',           'manager'),
  ('products',            'superadmin'),   ('products',            'account_owner'), ('products',            'admin'), ('products',            'org_admin'), ('products',            'manager'), ('products',            'employee'),
  ('products.summary',    'superadmin'),   ('products.summary',    'account_owner'), ('products.summary',    'admin'), ('products.summary',    'org_admin'), ('products.summary',    'manager'),
  ('feo_categories',      'superadmin'),   ('feo_categories',      'account_owner'), ('feo_categories',      'admin'), ('feo_categories',      'org_admin'),
  ('commercial_requests', 'superadmin'),   ('commercial_requests', 'account_owner'), ('commercial_requests', 'admin'), ('commercial_requests', 'org_admin'), ('commercial_requests', 'manager'),
  ('staff',               'superadmin'),   ('staff',               'account_owner'), ('staff',               'admin'), ('staff',               'org_admin'),
  ('reports',             'superadmin'),   ('reports',             'account_owner'), ('reports',             'admin'), ('reports',             'org_admin'), ('reports',             'manager'),
  ('plan',                'superadmin'),   ('plan',                'account_owner'), ('plan',                'admin'), ('plan',                'org_admin'), ('plan',                'manager'),
  ('system_incidents',    'superadmin'),   ('system_incidents',    'account_owner'), ('system_incidents',    'admin'), ('system_incidents',    'org_admin'),
  ('admin.organizations', 'superadmin'),
  ('admin.billing',       'superadmin'),   ('admin.billing',       'org_admin'),
  ('service_notes',       'superadmin'),   ('service_notes',       'account_owner'), ('service_notes',       'admin'), ('service_notes',       'org_admin'), ('service_notes',       'manager'), ('service_notes',       'employee'),
  ('advance_reports',     'superadmin'),   ('advance_reports',     'account_owner'), ('advance_reports',     'admin'), ('advance_reports',     'org_admin'), ('advance_reports',     'manager'), ('advance_reports',     'employee'),
  ('admin.settings',      'superadmin'),   ('admin.settings',      'account_owner'), ('admin.settings',      'admin'), ('admin.settings',      'org_admin'),
  ('chat',                'superadmin'),   ('chat',                'account_owner'), ('chat',                'admin'), ('chat',                'org_admin'), ('chat',                'manager'), ('chat',                'employee'),
  ('admin.roles',         'superadmin'),   ('admin.roles',         'account_owner'), ('admin.roles',         'admin'), ('admin.roles',         'org_admin'),
  -- Actions
  ('purchase.transition_status','superadmin'), ('purchase.transition_status','account_owner'), ('purchase.transition_status','admin'), ('purchase.transition_status','org_admin'), ('purchase.transition_status','manager'),
  ('wish.approve',        'superadmin'),   ('wish.approve',        'account_owner'), ('wish.approve',        'admin'), ('wish.approve',        'org_admin'), ('wish.approve',        'manager'),
  ('contract.delete',     'superadmin'),   ('contract.delete',     'account_owner'), ('contract.delete',     'admin'), ('contract.delete',     'org_admin'),
  ('payment.register',    'superadmin'),   ('payment.register',    'account_owner'), ('payment.register',    'admin'), ('payment.register',    'org_admin'), ('payment.register',    'manager'),
  ('subsidy.edit',        'superadmin'),   ('subsidy.edit',        'account_owner'), ('subsidy.edit',        'admin'), ('subsidy.edit',        'org_admin'),
  ('user.manage',         'superadmin'),   ('user.manage',         'account_owner'), ('user.manage',         'admin'), ('user.manage',         'org_admin')
)
INSERT INTO role_permissions (role_name, key, granted)
SELECT role_name, key, TRUE FROM matrix
ON CONFLICT (role_name, key) DO NOTHING;

-- ------------------------------------------------------------------ --
-- Seed can_publish → publication.create overrides                    --
-- ------------------------------------------------------------------ --
INSERT INTO user_org_permission_overrides (user_org_access_id, key, granted, updated_at)
SELECT uoa.id, 'publication.create', TRUE, NOW()
FROM user_org_access uoa
JOIN users u ON u.id = uoa.user_id
WHERE u.can_publish = TRUE AND uoa.org_id = u.org_id
ON CONFLICT (user_org_access_id, key) DO NOTHING;

-- ------------------------------------------------------------------ --
-- Final counts                                                       --
-- ------------------------------------------------------------------ --
SELECT 'tabs' as t, COUNT(*) FROM permission_tabs
UNION ALL SELECT 'actions', COUNT(*) FROM permission_actions
UNION ALL SELECT 'role_perm', COUNT(*) FROM role_permissions
UNION ALL SELECT 'overrides', COUNT(*) FROM user_org_permission_overrides;
