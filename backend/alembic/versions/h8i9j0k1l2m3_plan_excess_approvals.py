"""plan_excess_approvals + plan_excess_approval_steps — согласование превышения плана ФЭО

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-08-05 00:00:00.000000

Требование владельца (2026-08-05): «Если где-то превысил план ФЭО, значит
где-то надо снимать. Должны быть заблокированы действия, пока план-график не
загонять обратно в размеры ФЭО... согласование превышения должно быть цепочкой,
организации бывают разные, к директору не всегда простой сотрудник может
попасть».

plan_excess_approvals — запрос на согласование превышения плана над
финансированием (feo_categories.budget) одного узла дерева ФЭО:
  - feo_category_id  FK feo_categories ON DELETE CASCADE — узел, где обнаружено
    превышение
  - subsidy_id       FK subsidies — для GET-фильтра по субсидии
  - excess_amount    NUMERIC(15,2) — сумма превышения на момент запроса (снапшот)
  - plan_amount      NUMERIC(15,2) — плановая сумма узла (display) на момент запроса
  - budget_amount    NUMERIC(15,2) — финансирование по ФЭО узла на момент запроса
  - status           VARCHAR(20)   — pending / approved / rejected
  - mode             VARCHAR(20)   — sequential / parallel (режим цепочки, по
    образцу Wish.approval_mode — здесь у решения нет родительской сущности
    вроде wish, поэтому режим хранится прямо на запросе)
  - requested_by_id  FK users — кто запросил согласование
  - created_at, resolved_at, comment

plan_excess_approval_steps — шаги восходящей цепочки согласующих (по образцу
wish_approvals):
  - approval_id      FK plan_excess_approvals ON DELETE CASCADE
  - user_id          FK users (SET NULL — снапшот decided_by остаётся)
  - order_num        INTEGER — 0 = самый нижний в цепочке
  - status           VARCHAR(20) — pending / approved / rejected
  - decided_at, decided_by_user_id, comment

Идемпотентно (CREATE TABLE IF NOT EXISTS).
"""
from alembic import op
import sqlalchemy as sa

revision = 'h8i9j0k1l2m3'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS plan_excess_approvals (
            id SERIAL PRIMARY KEY,
            feo_category_id INTEGER NOT NULL REFERENCES feo_categories(id) ON DELETE CASCADE,
            subsidy_id INTEGER NOT NULL REFERENCES subsidies(id) ON DELETE CASCADE,
            excess_amount NUMERIC(15,2) NOT NULL,
            plan_amount NUMERIC(15,2),
            budget_amount NUMERIC(15,2),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            mode VARCHAR(20) NOT NULL DEFAULT 'sequential',
            requested_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ,
            comment TEXT
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_plan_excess_approvals_feo_category_id "
        "ON plan_excess_approvals (feo_category_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_plan_excess_approvals_subsidy_id "
        "ON plan_excess_approvals (subsidy_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_plan_excess_approvals_status "
        "ON plan_excess_approvals (status)"
    ))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS plan_excess_approval_steps (
            id SERIAL PRIMARY KEY,
            approval_id INTEGER NOT NULL REFERENCES plan_excess_approvals(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            order_num INTEGER NOT NULL DEFAULT 0,
            role_name VARCHAR(255),
            approver_full_name VARCHAR(500),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            comment TEXT,
            decided_at TIMESTAMPTZ,
            decided_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_plan_excess_approval_steps_approval_id "
        "ON plan_excess_approval_steps (approval_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS plan_excess_approval_steps"))
    op.execute(sa.text("DROP TABLE IF EXISTS plan_excess_approvals"))
