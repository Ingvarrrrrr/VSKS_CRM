"""purchase_paid_confirmations — запрос подтверждения «Оплачено» согласующими субсидии

План 2026-10-04-fadm-statement, п.3: recompute_purchase_payments больше не
переводит закупку в paid молча — заводит запись здесь, согласующий субсидии
(SubsidyApprover) подтверждает/отклоняет (см. app/routers/purchase_paid_confirmations.py).

Доработка (тот же день, до выката на прод — правим эту же миграцию, а не
заводим вторую): purchase_paid_confirmation_rejections — память об
отклонённых парах (purchase_id, bank_payment_id), чтобы следующий авто-
match-payments не предлагал ту же пару снова по кругу (см.
app/services/payment_lookup.py).

Идемпотентно (create_table через inspector-guard, CREATE UNIQUE INDEX IF NOT
EXISTS) — alembic upgrade head гоняется при каждом старте контейнера (migrate.py).

Revision ID: q4r6s8t0v2w4
Revises: p2q4r6s8t0v2
Create Date: 2026-10-04 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'q4r6s8t0v2w4'
down_revision = 'p2q4r6s8t0v2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("purchase_paid_confirmations"):
        op.create_table(
            "purchase_paid_confirmations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("purchase_id", sa.Integer(),
                      sa.ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("subsidy_id", sa.Integer(),
                      sa.ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("amount_confirmed", sa.Numeric(15, 2), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("decided_by", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("plan_excess_warning", sa.Text(), nullable=True),
        )
        op.create_index(
            "ix_purchase_paid_confirmations_purchase_id",
            "purchase_paid_confirmations", ["purchase_id"],
        )
        op.create_index(
            "ix_purchase_paid_confirmations_subsidy_id",
            "purchase_paid_confirmations", ["subsidy_id"],
        )
        print("[q4r6s8t0v2w4] purchase_paid_confirmations создана")
    else:
        # Доработка «оплата из выписки — факт» (та же миграция, до выката на
        # прод): таблица уже могла быть создана предыдущим прогоном этой же
        # миграции на этом окружении — добавляем колонку отдельно, идемпотентно.
        existing_cols = {c["name"] for c in inspector.get_columns("purchase_paid_confirmations")}
        if "plan_excess_warning" not in existing_cols:
            op.add_column(
                "purchase_paid_confirmations",
                sa.Column("plan_excess_warning", sa.Text(), nullable=True),
            )
            print("[q4r6s8t0v2w4] purchase_paid_confirmations.plan_excess_warning добавлен")

    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_purchase_paid_confirmation_one_pending "
        "ON purchase_paid_confirmations (purchase_id) WHERE status = 'pending'"
    ))

    if not inspector.has_table("purchase_paid_confirmation_rejections"):
        op.create_table(
            "purchase_paid_confirmation_rejections",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("confirmation_id", sa.Integer(),
                      sa.ForeignKey("purchase_paid_confirmations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("purchase_id", sa.Integer(),
                      sa.ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("bank_payment_id", sa.Integer(),
                      sa.ForeignKey("bank_payments.id", ondelete="CASCADE"), nullable=False),
            sa.Column("rejected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            "ix_paid_confirmation_rejections_purchase_id",
            "purchase_paid_confirmation_rejections", ["purchase_id"],
        )
        op.create_index(
            "ix_paid_confirmation_rejections_bank_payment_id",
            "purchase_paid_confirmation_rejections", ["bank_payment_id"],
        )
        print("[q4r6s8t0v2w4] purchase_paid_confirmation_rejections создана")

    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_paid_confirmation_rejection_pair "
        "ON purchase_paid_confirmation_rejections (purchase_id, bank_payment_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ux_paid_confirmation_rejection_pair"))
    op.execute(sa.text("DROP TABLE IF EXISTS purchase_paid_confirmation_rejections"))
    op.execute(sa.text("DROP INDEX IF EXISTS ux_purchase_paid_confirmation_one_pending"))
    op.execute(sa.text("DROP TABLE IF EXISTS purchase_paid_confirmations"))
