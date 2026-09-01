"""users.all_orgs_access — флаг «доступ ко всем организациям аккаунта»

Позволяет дать рядовому сотруднику видимость данных по ВСЕМ организациям его
аккаунта (root_org_id-дерево, см. app/auth/visibility.compute_account_contour_org_ids)
без заведения десятков/сотен строк user_org_access — по одной на организацию.
Роль пользователя НЕ меняется, флаг влияет только на охват данных в
get_org_filter (app/auth/jwt.py).

Idempotent: ADD COLUMN IF NOT EXISTS под inspector-guard. downgrade() — no-op
(колонка безвредна для старого кода: он её просто не читает).

Revision ID: z9a8b7c6d5e4
Revises: c4d5e6f7a8b9
Create Date: 2026-09-01 00:00:00.000000

Примечание (2026-09-01, выпрямление истории): изначально писалась поверх
f25e7fa19cbc параллельно с c4d5e6f7a8b9 (та же голова), из-за чего в git
образовались две головы. Чтобы не делать merge-миграцию (в проекте уже был
инцидент из-за merge, сославшегося на неотслеживаемую ревизию), цепочка
выпрямлена: down_revision перенесён на c4d5e6f7a8b9.
"""
import sqlalchemy as sa
from alembic import op

revision = 'z9a8b7c6d5e4'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'users' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('users')}
    if 'all_orgs_access' not in cols:
        op.execute(sa.text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS all_orgs_access "
            "BOOLEAN NOT NULL DEFAULT false"
        ))


def downgrade() -> None:
    # no-op: колонку намеренно не удаляем при откате (см. docstring)
    pass
