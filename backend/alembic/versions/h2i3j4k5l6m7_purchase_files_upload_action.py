"""add purchase_files.upload permission action

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-07-21 00:00:00.000000
"""
from alembic import op

revision = 'h2i3j4k5l6m7'
down_revision = 'g1h2i3j4k5l6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
INSERT INTO permission_actions (action_key, description)
VALUES ('purchase_files.upload', 'Документы закупки — загрузка')
ON CONFLICT (action_key) DO NOTHING;
"""
    )
    # Seed role_permissions for manager, org_admin, admin, account_owner, superadmin
    op.execute(
        """
INSERT INTO role_permissions (role_name, key, granted)
SELECT r.role, 'purchase_files.upload', TRUE
FROM (VALUES
    ('superadmin'), ('account_owner'), ('admin'), ('org_admin'), ('manager')
) AS r(role)
ON CONFLICT (role_name, key) DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE key = 'purchase_files.upload';"
    )
    op.execute(
        "DELETE FROM permission_actions WHERE action_key = 'purchase_files.upload';"
    )
