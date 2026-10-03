"""Защита входа от подбора пароля: блокировка аккаунта + token_version.

Три новые колонки users:
  failed_login_count     — неудачных попыток входа подряд (окно 15 мин)
  failed_login_first_at  — начало текущего окна подсчёта
  locked_until            — учётная запись заблокирована для входа до этого момента
  token_version           — инкрементируется при каждой смене пароля, кладётся
                            в JWT claim "tv"; get_current_user (app/auth/jwt.py)
                            отклоняет токен, выпущенный ДО смены пароля.

См. backend/app/auth/account_lockout.py и backend/app/auth/token_version.py.

Идемпотентно (ADD COLUMN IF NOT EXISTS) — alembic upgrade head/heads гоняется
при каждом старте контейнера (backend/migrate.py), повторный прогон должен
быть no-op.

Revision ID: n7p9q1r3s5t7
Revises: d3e5f7g9h1j3
Create Date: 2026-10-03 00:00:01.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'n7p9q1r3s5t7'
down_revision = 'd3e5f7g9h1j3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER NOT NULL DEFAULT 0"
    ))
    op.execute(sa.text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_first_at TIMESTAMPTZ"
    ))
    op.execute(sa.text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ"
    ))
    op.execute(sa.text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS token_version"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS locked_until"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS failed_login_first_at"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS failed_login_count"))
