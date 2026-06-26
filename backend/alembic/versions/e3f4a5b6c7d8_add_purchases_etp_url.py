"""add purchases.etp_url — ссылка на конкурсную процедуру ЭТП

Revision ID: e3f4a5b6c7d8
Revises: d4e5f6a7b8c9
Create Date: 2026-06-24 10:00:00.000000

Признак «закупка проводилась через ЭТП» = ссылка заполнена (непустой URL).
Отдельный boolean не требуется.
"""
import sqlalchemy as sa
from alembic import op

revision = 'e3f4a5b6c7d8'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: prod-схему строит check_schema (runtime-DDL), колонка могла
    # появиться раньше. Plain ADD COLUMN падал бы DuplicateColumnError и валил старт.
    op.execute(sa.text("ALTER TABLE purchases ADD COLUMN IF NOT EXISTS etp_url TEXT"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE purchases DROP COLUMN IF EXISTS etp_url"))
