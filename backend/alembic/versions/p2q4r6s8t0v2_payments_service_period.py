"""payments.service_period — месяц оказания услуги для помесячных закупок.

Помесячная закупка (Purchase.is_monthly_payment=True: уборка, связь, предрейсовые
осмотры) получает платежи одной суммы за разные месяцы — каждый платёж обязан
лечь на СВОЙ месяц оказания, см. app/services/payment_service_period.py::resolve_service_period.

service_period — первое число месяца оказания (DATE), NULL для всех платежей не
помесячных закупок (и для помесячных — пока месяц не определён). Частичный уникальный
индекс (purchase_id, service_period) WHERE service_period IS NOT NULL AND
matched_confirmed — тот же паттерн защиты, что у ix_payments_purchase_basis_key_uniq
(basis_key), не второй механизм.

Идемпотентно (ADD COLUMN IF NOT EXISTS / CREATE UNIQUE INDEX IF NOT EXISTS) —
alembic upgrade head гоняется при каждом старте контейнера (migrate.py).

Revision ID: p2q4r6s8t0v2
Revises: p1q3r5s7t9v1
Create Date: 2026-10-04 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'p2q4r6s8t0v2'
down_revision = 'p1q3r5s7t9v1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS service_period DATE"
    ))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_payments_purchase_service_period_uniq "
        "ON payments (purchase_id, service_period) "
        "WHERE service_period IS NOT NULL AND matched_confirmed"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_payments_purchase_service_period_uniq"))
    op.execute(sa.text("ALTER TABLE payments DROP COLUMN IF EXISTS service_period"))
