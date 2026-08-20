"""wish_approvals: decided_by_username — снапшот ФИО решившего

Задача (2026-08-20, бэкенд): «кто согласовал за кого». UI должен показывать
ФИО решившего согласующего, а не только числовой decided_by_user_id.
Переименование/удаление пользователя не должно стирать историю решения —
поэтому снапшот ФИО на момент решения, по образцу
app/models/purchase_approval.py::decided_by_username (см. миграцию
purchase_approvals в этом же versions/).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  wish_approvals:
    - decided_by_username  VARCHAR(100), nullable

downgrade(): DROP COLUMN IF EXISTS.

Revision ID: a3f7c2d8b6e1
Revises: c7d9f2a1b3e5
Create Date: 2026-08-20 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a3f7c2d8b6e1'
down_revision = 'c7d9f2a1b3e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE wish_approvals ADD COLUMN IF NOT EXISTS decided_by_username VARCHAR(100)"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE wish_approvals DROP COLUMN IF EXISTS decided_by_username"
    ))
