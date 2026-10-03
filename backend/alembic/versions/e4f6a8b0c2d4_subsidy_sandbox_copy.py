"""Копия субсидии для экспериментов (владелец, план breezy-mixing-lovelace.md,
Часть Б, 03.10.2026).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  - subsidies.is_sandbox BOOLEAN NOT NULL DEFAULT false — «песочница»: копия
    субсидии для экспериментов, исключается из итогов дашборда/аккаунта, не
    шлёт уведомлений/задач.
  - subsidies.copied_from_id INT NULL (FK subsidies.id, ON DELETE SET NULL) —
    из какой субсидии сделана эта копия (NULL у обычных субсидий и у
    оригиналов).

Revision ID: e4f6a8b0c2d4
Revises: b1c3d5e7f9a1
Create Date: 2026-10-03 00:00:00.000000
"""
from alembic import op

revision = 'e4f6a8b0c2d4'
down_revision = 'b1c3d5e7f9a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE subsidies ADD COLUMN IF NOT EXISTS is_sandbox BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE subsidies ADD COLUMN IF NOT EXISTS copied_from_id INTEGER NULL"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'subsidies_copied_from_id_fkey'
            ) THEN
                ALTER TABLE subsidies
                    ADD CONSTRAINT subsidies_copied_from_id_fkey
                    FOREIGN KEY (copied_from_id) REFERENCES subsidies(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_subsidies_is_sandbox ON subsidies (is_sandbox)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_subsidies_is_sandbox")
    op.execute("ALTER TABLE subsidies DROP CONSTRAINT IF EXISTS subsidies_copied_from_id_fkey")
    op.execute("ALTER TABLE subsidies DROP COLUMN IF EXISTS copied_from_id")
    op.execute("ALTER TABLE subsidies DROP COLUMN IF EXISTS is_sandbox")
