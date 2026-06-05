"""org_admin gets full permission set (= admin) by default

Revision ID: d1e2f3a4b5c6
Revises: c9f2a3b4d5e6
Create Date: 2026-06-05 00:00:00.000000

Bug: org_admin (напр. Артеева в Донецком отделении) не мог добавить сотрудника —
'user.manage' был выдан только superadmin/account_owner/admin, без org_admin.
Семантика роли: «Админ организации по умолчанию может делать всё» в рамках своей
орг (данные скоупятся отдельно через get_org_filter). Поэтому выдаём org_admin
ВСЕ ключи, которыми обладает admin — идемпотентно (ON CONFLICT DO NOTHING),
закрывая и текущий пробел (user.manage), и будущие новые экшены.
"""
from alembic import op

revision = 'd1e2f3a4b5c6'
down_revision = 'c9f2a3b4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
INSERT INTO role_permissions (role_name, key, granted)
SELECT 'org_admin', rp.key, TRUE
FROM role_permissions rp
WHERE rp.role_name = 'admin' AND rp.granted = TRUE
ON CONFLICT (role_name, key) DO NOTHING;
"""
    )


def downgrade() -> None:
    # Минимальный откат: снимаем только тот ключ, ради которого писалась миграция.
    # Полный реверс копирования небезопасен (нельзя отличить унаследованные ключи
    # от настроенных вручную).
    op.execute(
        "DELETE FROM role_permissions WHERE role_name = 'org_admin' AND key = 'user.manage';"
    )
