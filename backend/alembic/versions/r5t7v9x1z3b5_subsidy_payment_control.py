"""subsidy_payment_control — контрольные суммы «выписка ↔ закупки» по субсидии

План .planning/quick/2026-10-05-payment-control/PLAN.md, раздел 1:
- subsidy_payment_control_codes — выбор субсидии, какие статьи расходов
  обязаны найти закупку (по умолчанию, если записей нет — коды с
  is_procurement=true, см. app/services/subsidy_payment_control.py).
- purchases.created_from_bank_payment_id — закупка заведена без заявки прямо
  из строки выписки (см. app/services/purchase_from_bank_payment.py).
- expense_codes 0813001 (Страховые взносы ОСС, не закупка) и 0300033 (товар,
  закупка) — коды, встречавшиеся в живой выписке ФАДМ, но отсутствовавшие в
  справочнике (план, Контекст/Факты).

Идемпотентно (inspector-guard / ON CONFLICT DO NOTHING) — alembic upgrade
head гоняется при каждом старте контейнера (migrate.py).

Revision ID: r5t7v9x1z3b5
Revises: q4r6s8t0v2w4
Create Date: 2026-10-05 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'r5t7v9x1z3b5'
down_revision = 'q4r6s8t0v2w4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("subsidy_payment_control_codes"):
        op.create_table(
            "subsidy_payment_control_codes",
            sa.Column("subsidy_id", sa.Integer(),
                      sa.ForeignKey("subsidies.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("code", sa.String(10), primary_key=True),
        )
        print("[r5t7v9x1z3b5] subsidy_payment_control_codes создана")

    purchases_cols = {c["name"] for c in inspector.get_columns("purchases")}
    if "created_from_bank_payment_id" not in purchases_cols:
        op.add_column(
            "purchases",
            sa.Column(
                "created_from_bank_payment_id", sa.Integer(),
                sa.ForeignKey("bank_payments.id", ondelete="SET NULL"), nullable=True,
            ),
        )
        op.create_index(
            "ix_purchases_created_from_bank_payment_id",
            "purchases", ["created_from_bank_payment_id"],
        )
        print("[r5t7v9x1z3b5] purchases.created_from_bank_payment_id добавлен")

    op.execute(sa.text(
        """
        INSERT INTO expense_codes (code, parent_code, name, kind, is_procurement, is_active)
        VALUES
            ('0813001', '0813', 'Страховые взносы ОСС', 'налог', false, true),
            ('0300033', '0300', 'Товары (код 0300033)', 'товар', true, true)
        ON CONFLICT (code) DO NOTHING
        """
    ))
    print("[r5t7v9x1z3b5] expense_codes 0813001/0300033 добавлены (если отсутствовали)")


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM expense_codes WHERE code IN ('0813001', '0300033')"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_purchases_created_from_bank_payment_id"))
    op.execute(sa.text("ALTER TABLE purchases DROP COLUMN IF EXISTS created_from_bank_payment_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS subsidy_payment_control_codes"))
