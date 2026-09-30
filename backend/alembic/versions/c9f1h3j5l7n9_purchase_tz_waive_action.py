"""add purchase.tz_waive permission action

Владелец (30.09, уточнение к заявке №92): «Это должно быть ОТДЕЛЬНОЕ
разрешение в ролях — кому можно отменять необходимость ТЗ, а кому нет».
Данные зеркалят идемпотентный сид app.startup.permission_seeds.py::
_purchase_tz_waive_action() (тот же source of truth, что читает
backend/scripts/export_dictionaries.py для frontend/src/data/dictionaries.json)
— эта миграция просто применяет их немедленно на существующих БД, не дожидаясь
перезапуска приложения.

Revision ID: c9f1h3j5l7n9
Revises: b8e0g2i4k6m8
Create Date: 2026-09-30 00:00:00.000000
"""
from alembic import op

revision = 'c9f1h3j5l7n9'
down_revision = 'b8e0g2i4k6m8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
INSERT INTO permission_actions (action_key, description)
VALUES ('purchase.tz_waive', 'Отмена необходимости ТЗ по решению согласующего')
ON CONFLICT (action_key) DO NOTHING;
"""
    )
    # Дефолт: superadmin/account_owner/admin=TRUE; org_admin/manager/employee=FALSE
    # (владелец раздаст org_admin/manager сам, где нужно) — те же значения,
    # что в permission_seeds.py::_purchase_tz_waive_action.
    op.execute(
        """
INSERT INTO role_permissions (role_name, key, granted)
SELECT r.role, 'purchase.tz_waive', TRUE
FROM (VALUES
    ('superadmin'), ('account_owner'), ('admin')
) AS r(role)
ON CONFLICT (role_name, key) DO NOTHING;
"""
    )
    op.execute(
        """
INSERT INTO role_permissions (role_name, key, granted)
SELECT r.role, 'purchase.tz_waive', FALSE
FROM (VALUES
    ('org_admin'), ('manager'), ('employee')
) AS r(role)
ON CONFLICT (role_name, key) DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE key = 'purchase.tz_waive';"
    )
    op.execute(
        "DELETE FROM permission_actions WHERE action_key = 'purchase.tz_waive';"
    )
