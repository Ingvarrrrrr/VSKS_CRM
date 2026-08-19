"""wishes: rejected_by + rejected_at — кто отклонил заявку

ПРИМЕЧАНИЕ (2026-08-19, параллельная волна): исходный revision id этого файла
('a1b2c3d4e5f6') совпал с уже существующим `a1b2c3d4e5f6_wish_members.py`
(июнь 2026, down_revision='f3a4b5c6d7e8') — два разных файла с одинаковым
revision ломали весь граф alembic («Cycle is detected in revisions») для ЛЮБОЙ
миграции, не только этой. Id переименован в 'd6f2a9c1e4b8', чтобы разблокировать
`alembic upgrade head`; вся DDL-логика (upgrade/downgrade) не тронута.

Revision ID: d6f2a9c1e4b8
Revises: f517d1525628
Create Date: 2026-08-19 00:00:00.000000

Владелец (2026-08-19): «нужно, чтобы было видно, кто отклонил. Так удобнее
сходить внутри офиса и спросить, что не так, или просто связаться».

Отклонение заявки (и через прямой /wishes/{id}/reject, и через цепочку
согласующих /wishes/{id}/approvers/{aid}/decide) сбрасывает решения ВСЕХ
согласующих обратно в pending (см. wishes.py::_reset_approvals) — включая
решение самого отклонившего. После сброса по WishApproval уже нельзя понять,
кто отклонил. rejected_by/rejected_at хранят это на самой заявке, отдельно
от цепочки — переживают сброс.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  wishes:
    - rejected_by  INTEGER, FK users.id ON DELETE SET NULL
    - rejected_at  TIMESTAMPTZ

downgrade(): DROP COLUMN IF EXISTS для обеих колонок.
"""
from alembic import op
import sqlalchemy as sa

revision = 'd6f2a9c1e4b8'
down_revision = 'f517d1525628'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE wishes ADD COLUMN IF NOT EXISTS rejected_by INTEGER"
    ))
    op.execute(sa.text(
        "ALTER TABLE wishes ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ"
    ))

    # FK добавляем отдельно, тоже идемпотентно (через information_schema —
    # у ALTER TABLE ADD CONSTRAINT нет IF NOT EXISTS в PostgreSQL).
    op.execute(sa.text(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'wishes_rejected_by_fkey'
                  AND table_name = 'wishes'
            ) THEN
                ALTER TABLE wishes
                    ADD CONSTRAINT wishes_rejected_by_fkey
                    FOREIGN KEY (rejected_by) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE wishes DROP CONSTRAINT IF EXISTS wishes_rejected_by_fkey"))
    op.execute(sa.text("ALTER TABLE wishes DROP COLUMN IF EXISTS rejected_at"))
    op.execute(sa.text("ALTER TABLE wishes DROP COLUMN IF EXISTS rejected_by"))
