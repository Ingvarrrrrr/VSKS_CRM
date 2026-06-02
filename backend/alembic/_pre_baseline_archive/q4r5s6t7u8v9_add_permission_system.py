"""add permission system: tabs, actions, role_permissions, user_org_overrides + seed

Revision ID: q4r5s6t7u8v9
Revises: p3q4r5s6t7u8
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa

revision = 'q4r5s6t7u8v9'
down_revision = 'p3q4r5s6t7u8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # Step A — create 4 tables                                            #
    # ------------------------------------------------------------------ #
    op.create_table(
        'permission_tabs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tab_key', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('title', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_permission_tabs_tab_key', 'permission_tabs', ['tab_key'], unique=True)

    op.create_table(
        'permission_actions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('action_key', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('description', sa.String(256), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_permission_actions_action_key', 'permission_actions', ['action_key'], unique=True)

    op.create_table(
        'role_permissions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('role_name', sa.String(32), nullable=False, index=True),
        sa.Column('key', sa.String(64), nullable=False, index=True),
        sa.Column('granted', sa.Boolean(), nullable=False, default=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('role_name', 'key', name='uq_role_perm'),
    )
    op.create_index('ix_role_permissions_role_name', 'role_permissions', ['role_name'])
    op.create_index('ix_role_permissions_key', 'role_permissions', ['key'])

    op.create_table(
        'user_org_permission_overrides',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_org_access_id', sa.Integer(), sa.ForeignKey('user_org_access.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('key', sa.String(64), nullable=False, index=True),
        sa.Column('granted', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('user_org_access_id', 'key', name='uq_uoa_override'),
    )
    op.create_index('ix_user_org_permission_overrides_user_org_access_id', 'user_org_permission_overrides', ['user_org_access_id'])
    op.create_index('ix_user_org_permission_overrides_key', 'user_org_permission_overrides', ['key'])

    # ------------------------------------------------------------------ #
    # Step B — seed permission_tabs (23 rows, idempotent)                 #
    # ------------------------------------------------------------------ #
    connection = op.get_bind()

    tabs = [
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
        ('admin.roles', 'Роли'),
    ]
    for tab_key, title in tabs:
        connection.execute(
            sa.text(
                "INSERT INTO permission_tabs (tab_key, title) VALUES (:tab_key, :title)"
                " ON CONFLICT (tab_key) DO NOTHING"
            ),
            {"tab_key": tab_key, "title": title},
        )

    # ------------------------------------------------------------------ #
    # Step C — seed permission_actions (7 rows, idempotent)               #
    # ------------------------------------------------------------------ #
    actions = [
        ('purchase.transition_status', 'Перевод статуса закупки'),
        ('wish.approve', 'Одобрение заявки'),
        ('contract.delete', 'Удаление договора'),
        ('payment.register', 'Регистрация выплаты'),
        ('publication.create', 'Создание публикации'),
        ('subsidy.edit', 'Редактирование/удаление субсидии'),
        ('user.manage', 'Управление персоналом'),
    ]
    for action_key, description in actions:
        connection.execute(
            sa.text(
                "INSERT INTO permission_actions (action_key, description) VALUES (:action_key, :description)"
                " ON CONFLICT (action_key) DO NOTHING"
            ),
            {"action_key": action_key, "description": description},
        )

    # ------------------------------------------------------------------ #
    # Step D — seed role_permissions from the hardcoded matrix            #
    # ------------------------------------------------------------------ #
    ADMIN = {'superadmin', 'account_owner', 'admin', 'org_admin'}
    MANAGER = ADMIN | {'manager'}
    ALL = MANAGER | {'employee'}
    OWNER = {'superadmin', 'account_owner'}

    matrix = {
        'dashboard':                MANAGER,
        'dashboard.radar':          MANAGER,
        'my_tasks':                 ALL,
        'wishes':                   ALL,
        'subsidies':                ADMIN,
        'purchases':                ALL,
        'contractors':              ALL,
        'contracts':                MANAGER,
        'products':                 ALL,
        'products.summary':         MANAGER,
        'feo_categories':           ADMIN,
        'commercial_requests':      MANAGER,
        'staff':                    ADMIN,
        'reports':                  MANAGER,
        'plan':                     MANAGER,
        'system_incidents':         ADMIN,
        'admin.organizations':      {'superadmin'},
        'admin.billing':            {'superadmin', 'org_admin'},
        'service_notes':            ALL,
        'advance_reports':          ALL,
        'admin.settings':           ADMIN,
        'chat':                     ALL,
        'admin.roles':              ADMIN,
        # Actions
        'purchase.transition_status': MANAGER,
        'wish.approve':             MANAGER,
        'contract.delete':          ADMIN,
        'payment.register':         MANAGER,
        'subsidy.edit':             ADMIN,
        'user.manage':              {'superadmin', 'account_owner', 'admin'},
        # publication.create: NOT seeded into role_permissions —
        # migrated per-user from can_publish flag in Step E below
    }

    for key, roles in matrix.items():
        for role_name in roles:
            connection.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_name, key, granted)"
                    " VALUES (:role_name, :key, :granted)"
                    " ON CONFLICT (role_name, key) DO NOTHING"
                ),
                {"role_name": role_name, "key": key, "granted": True},
            )

    # ------------------------------------------------------------------ #
    # Step E — can_publish data migration → publication.create override   #
    # ------------------------------------------------------------------ #
    connection.execute(
        sa.text("""
            INSERT INTO user_org_permission_overrides (user_org_access_id, key, granted, updated_at)
            SELECT uoa.id, 'publication.create', TRUE, NOW()
            FROM user_org_access uoa
            JOIN users u ON u.id = uoa.user_id
            WHERE u.can_publish = TRUE AND uoa.org_id = u.org_id
            ON CONFLICT (user_org_access_id, key) DO NOTHING
        """)
    )


def downgrade() -> None:
    op.drop_table('user_org_permission_overrides')
    op.drop_table('role_permissions')
    op.drop_table('permission_actions')
    op.drop_table('permission_tabs')
