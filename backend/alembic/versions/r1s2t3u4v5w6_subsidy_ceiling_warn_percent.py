"""subsidies.ceiling_warn_percent — настраиваемый порог предупреждения о подходе к потолку

Владелец (2026-08-30): «Надо предупреждение выдавать, когда сумма
заказанного будет приближаться к потолку субсидии. К примеру к 90
процентов». Порог настраиваемый НА КАЖДОЙ субсидии (умолчание 90%) —
хранится колонкой, не хардкодом (см. Lessons.md:
feedback_stage_choices_must_survive — выбранное пользователем не смеет
меняться само/эвристикой).

«Потолок» субсидии — это calculate_budget_from_categories (тот же источник,
что и жёсткий гейт PLAN_OVER_SUBSIDY_CEILING в
app.services.feo_plan.assert_no_unapproved_excess), порог сравнивается с
суммой обязательств (см. app.services.feo_plan.calculate_ceiling_forecast*).

Idempotent: ADD COLUMN IF NOT EXISTS через inspector-guard (стандартный
паттерн проекта, см. n1o2p3q4r5s6_add_commitment_quarter_planned_payment_month.py).

Revision ID: r1s2t3u4v5w6
Revises: p9r2t5v8x1z4
Create Date: 2026-08-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'r1s2t3u4v5w6'
down_revision = 'a3f7c2d8b6e1'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if 'subsidies' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('subsidies')}
    if 'ceiling_warn_percent' not in cols:
        op.add_column(
            'subsidies',
            sa.Column('ceiling_warn_percent', sa.Numeric(5, 2), nullable=True, server_default='90'),
        )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if 'subsidies' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('subsidies')}
    if 'ceiling_warn_percent' in cols:
        op.drop_column('subsidies', 'ceiling_warn_percent')
