"""phase22 permission seed: payment_registry tab + import/confirm/unbind actions

Revision ID: z3a4b5c6d7e8
Revises: y2z3a4b5c6d7
Create Date: 2026-04-27

Phase 22.04 — seeds permission_tabs and permission_actions for the bank
statement import workflow, then grants them to the appropriate roles via
role_permissions.  All inserts are idempotent (ON CONFLICT DO NOTHING).
"""
from alembic import op
import sqlalchemy as sa

revision = 'z3a4b5c6d7e8'
down_revision = 'y2z3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # ------------------------------------------------------------------
    # 1. permission_tabs — добавляем 'payment_registry'
    # ------------------------------------------------------------------
    connection.execute(
        sa.text("""
            INSERT INTO permission_tabs (tab_key, title)
            VALUES ('payment_registry', 'Реестр платежей')
            ON CONFLICT (tab_key) DO NOTHING
        """)
    )

    # ------------------------------------------------------------------
    # 2. permission_actions — 3 новых action
    # ------------------------------------------------------------------
    new_actions = [
        ('payment.import',  'Импорт банковских выписок'),
        ('payment.confirm', 'Подтверждение матча платежа'),
        ('payment.unbind',  'Откат подтверждения платежа'),
    ]
    for action_key, description in new_actions:
        connection.execute(
            sa.text("""
                INSERT INTO permission_actions (action_key, description)
                VALUES (:action_key, :description)
                ON CONFLICT (action_key) DO NOTHING
            """),
            {"action_key": action_key, "description": description},
        )

    # ------------------------------------------------------------------
    # 3. role_permissions seed
    #
    # admin / manager / superadmin / account_owner:
    #   tab payment_registry + all 3 actions → granted
    #
    # org_admin:
    #   tab payment_registry + payment.confirm → granted
    #
    # employee: no access (registry платежей — не для рядового сотрудника)
    # ------------------------------------------------------------------
    FULL_ACCESS_ROLES = {'superadmin', 'account_owner', 'admin', 'manager'}
    ORG_ADMIN_KEYS = {'payment_registry', 'payment.confirm'}

    full_keys = {'payment_registry', 'payment.import', 'payment.confirm', 'payment.unbind'}

    for role in FULL_ACCESS_ROLES:
        for key in full_keys:
            connection.execute(
                sa.text("""
                    INSERT INTO role_permissions (role_name, key, granted)
                    VALUES (:role_name, :key, :granted)
                    ON CONFLICT (role_name, key) DO NOTHING
                """),
                {"role_name": role, "key": key, "granted": True},
            )

    for key in ORG_ADMIN_KEYS:
        connection.execute(
            sa.text("""
                INSERT INTO role_permissions (role_name, key, granted)
                VALUES (:role_name, :key, :granted)
                ON CONFLICT (role_name, key) DO NOTHING
            """),
            {"role_name": "org_admin", "key": key, "granted": True},
        )


def downgrade() -> None:
    connection = op.get_bind()

    keys_to_remove = [
        'payment_registry', 'payment.import', 'payment.confirm', 'payment.unbind',
    ]
    for key in keys_to_remove:
        connection.execute(
            sa.text("DELETE FROM role_permissions WHERE key = :key"),
            {"key": key},
        )
        connection.execute(
            sa.text("DELETE FROM permission_actions WHERE action_key = :key"),
            {"key": key},
        )

    connection.execute(
        sa.text("DELETE FROM permission_tabs WHERE tab_key = 'payment_registry'")
    )
