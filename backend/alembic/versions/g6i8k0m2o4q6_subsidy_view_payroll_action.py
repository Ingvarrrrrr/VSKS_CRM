"""add subsidy.view_payroll permission action

Владелец (решение 21.10.2026): «для того чтобы в статистике ФОТ отображался
у человека должна быть отдельная галочка. Если её нет, то он видит только
товары и услуги» — на вопрос «где прятать» ответ «Везде» (карточки
дашборда, реестр закупок, дерево ФЭО, выгрузка в Excel). Данные зеркалят
идемпотентный сид app.startup.permission_seeds.py::_subsidy_view_payroll_action()
(тот же source of truth, что читает backend/scripts/export_dictionaries.py
для frontend/src/data/dictionaries.json) — эта миграция просто применяет их
немедленно на существующих БД, не дожидаясь перезапуска приложения.

Revision ID: g6i8k0m2o4q6
Revises: f4h6j8l0n2p4
Create Date: 2026-10-21 00:00:00.000000
"""
from alembic import op

revision = 'g6i8k0m2o4q6'
down_revision = 'h7j9l1n3p5r7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
INSERT INTO permission_actions (action_key, description)
VALUES ('subsidy.view_payroll', 'Видеть ФОТ (выплаты персоналу): суммы в статистике, статьи в дереве ФЭО, закупки в реестре')
ON CONFLICT (action_key) DO NOTHING;
"""
    )
    # Дефолт: superadmin/account_owner=TRUE; admin/org_admin/manager/employee=FALSE
    # (владелец раздаст индивидуально через UserOrgPermissionOverride) — те же
    # значения, что в permission_seeds.py::_subsidy_view_payroll_action.
    op.execute(
        """
INSERT INTO role_permissions (role_name, key, granted)
SELECT r.role, 'subsidy.view_payroll', TRUE
FROM (VALUES
    ('superadmin'), ('account_owner')
) AS r(role)
ON CONFLICT (role_name, key) DO NOTHING;
"""
    )
    op.execute(
        """
INSERT INTO role_permissions (role_name, key, granted)
SELECT r.role, 'subsidy.view_payroll', FALSE
FROM (VALUES
    ('admin'), ('org_admin'), ('manager'), ('employee')
) AS r(role)
ON CONFLICT (role_name, key) DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE key = 'subsidy.view_payroll';"
    )
    op.execute(
        "DELETE FROM permission_actions WHERE action_key = 'subsidy.view_payroll';"
    )
