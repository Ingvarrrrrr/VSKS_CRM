"""Согласующий может освободить заявку/закупку от ТЗ — wishes/purchases.tz_not_required

Владелец (30.09, дословно): «ТЗ нужно для всех товаров, но исключение
работает для авансовых, и у согласующего должна быть такая возможность.
В заявке много мелочёвки — я как согласующий должен иметь возможность, чтобы
товары уходили без ТЗ». Живой случай — заявка №92 «Расходные материалы для
постройки и проведения слёта» (16 позиций канцелярии/расходников).

До этой миграции освобождение от гейта «решите дубли строк ТЗ перед
генерацией документов» (см. app/services/documents/contexts.py::
_require_tz_duplicates_resolved_for_doc) было зашито прямо в гейте как
`purchase_method == 'advance'` — единственное место во всём проекте, которое
на это смотрело. Теперь тот же гейт (через единый хелпер
app.services.tz_items.tz_required, ПРАВИЛО №6) освобождает и любую закупку
с tz_not_required=True.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  wishes:
    - tz_not_required       BOOLEAN NOT NULL DEFAULT false — согласующий
      поставил галочку «Без ТЗ (мелкие закупки)» при решении по заявке
      (POST /wishes/{id}/approve, POST /wishes/{id}/approvers/{id}/decide).
    - tz_waived_by_user_id  INTEGER NULL FK users.id ON DELETE SET NULL —
      кто именно поставил галочку.
  purchases:
    - tz_not_required       BOOLEAN NOT NULL DEFAULT false — копия флага
      заявки, переносится при распределении в закупку
      (app/services/wish_distribution.py); также источник для гейта ТЗ.
    - tz_waived_by_user_id  INTEGER NULL FK users.id ON DELETE SET NULL.

Downgrade — DROP COLUMN IF EXISTS (тоже идемпотентно).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'b8e0g2i4k6m8'
down_revision = "a3c5e7g9i1k3"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    wishes_cols = {c["name"] for c in inspector.get_columns("wishes")}
    if "tz_not_required" not in wishes_cols:
        op.add_column(
            "wishes",
            sa.Column("tz_not_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "tz_waived_by_user_id" not in wishes_cols:
        op.add_column(
            "wishes",
            sa.Column("tz_waived_by_user_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_wishes_tz_waived_by_user_id_users",
            "wishes", "users",
            ["tz_waived_by_user_id"], ["id"],
            ondelete="SET NULL",
        )

    purchases_cols = {c["name"] for c in inspector.get_columns("purchases")}
    if "tz_not_required" not in purchases_cols:
        op.add_column(
            "purchases",
            sa.Column("tz_not_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "tz_waived_by_user_id" not in purchases_cols:
        op.add_column(
            "purchases",
            sa.Column("tz_waived_by_user_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_purchases_tz_waived_by_user_id_users",
            "purchases", "users",
            ["tz_waived_by_user_id"], ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    purchases_cols = {c["name"] for c in inspector.get_columns("purchases")}
    if "tz_waived_by_user_id" in purchases_cols:
        op.drop_constraint("fk_purchases_tz_waived_by_user_id_users", "purchases", type_="foreignkey")
        op.drop_column("purchases", "tz_waived_by_user_id")
    if "tz_not_required" in purchases_cols:
        op.drop_column("purchases", "tz_not_required")

    wishes_cols = {c["name"] for c in inspector.get_columns("wishes")}
    if "tz_waived_by_user_id" in wishes_cols:
        op.drop_constraint("fk_wishes_tz_waived_by_user_id_users", "wishes", type_="foreignkey")
        op.drop_column("wishes", "tz_waived_by_user_id")
    if "tz_not_required" in wishes_cols:
        op.drop_column("wishes", "tz_not_required")
