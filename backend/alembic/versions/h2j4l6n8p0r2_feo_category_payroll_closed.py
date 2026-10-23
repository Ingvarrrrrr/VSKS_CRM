"""feo_categories: payroll_closed («Закрыть ФОТ по статье»)

Владелец, 22.10.2026, план humble-stirring-emerson.md, шаг 1, вариант (в):
кнопка на статье ФОТ дерева ФЭО — нажали → план статьи = фактически
выплачено/законтрактовано (защита «ФОТ не даёт экономии»,
feo_plan_common._order_substituted_plan(is_payroll=...), снимается ТОЛЬКО
для этой статьи), невыплаченный остаток уходит в «Свободно»; «Отменить
закрытие» возвращает защиту. Кто/когда закрыл — отдельные колонки (для
подписи на экране); «сколько высвобождено» в момент закрытия пишется в
entity_changes через app.services.feo_history (ENTITY_FEO_CATEGORY,
source=SOURCE_MANUAL) — вторую таблицу истории не заводим (ПРАВИЛО №6).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  feo_categories:
    - payroll_closed            BOOLEAN NOT NULL DEFAULT false
    - payroll_closed_by_user_id INTEGER NULL, FK users.id ON DELETE SET NULL
    - payroll_closed_at         TIMESTAMPTZ NULL

Downgrade — DROP COLUMN IF EXISTS (тоже идемпотентно).

Revision ID: h2j4l6n8p0r2
Revises: g6i8k0m2o4q6
Create Date: 2026-10-23 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'h2j4l6n8p0r2'
down_revision = 'g6i8k0m2o4q6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_categories")}

    if "payroll_closed" not in existing_cols:
        op.add_column(
            "feo_categories",
            sa.Column("payroll_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "payroll_closed_by_user_id" not in existing_cols:
        op.add_column(
            "feo_categories",
            sa.Column(
                "payroll_closed_by_user_id", sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
            ),
        )
    if "payroll_closed_at" not in existing_cols:
        op.add_column(
            "feo_categories",
            sa.Column("payroll_closed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_categories")}

    if "payroll_closed_at" in existing_cols:
        op.drop_column("feo_categories", "payroll_closed_at")
    if "payroll_closed_by_user_id" in existing_cols:
        op.drop_column("feo_categories", "payroll_closed_by_user_id")
    if "payroll_closed" in existing_cols:
        op.drop_column("feo_categories", "payroll_closed")
