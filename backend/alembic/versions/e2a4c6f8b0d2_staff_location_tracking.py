"""Отслеживание местоположения сотрудников — смены + точки GPS

Владелец (организация спасателей, 2026-09): «нужно понимать, кто где
находится — в аварийной ситуации это вопрос безопасности». Согласия
сотрудников владелец берёт на себя. Передача включается/выключается кнопкой
«Я на смене», история хранится 30 дней (автоудаление — см.
app/__init__.py::_staff_location_cleanup_loop). ТОЛЬКО BACKEND в этой фазе.

Создаёт (идемпотентно, под inspector.has_table() guard, по образцу
p9r2t5v8x1z4_price_freshness_and_history.py / c9d1e3f5a7b9_body_type_icon_overrides.py):

  - staff_shifts:
      user_id     FK users(id) ON DELETE CASCADE, NOT NULL
      started_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
      ended_at    TIMESTAMPTZ  NULL
      is_active   BOOLEAN      NOT NULL DEFAULT true
      Частичный UNIQUE INDEX (user_id) WHERE is_active — одна активная смена
      на пользователя одновременно.

  - staff_location_points:
      user_id      FK users(id) ON DELETE CASCADE, NOT NULL — каскад при
                   удалении пользователя (задание п.1).
      lat, lon     DOUBLE PRECISION NOT NULL
      accuracy_m   DOUBLE PRECISION NULL
      recorded_at  TIMESTAMPTZ NOT NULL — время фиксации на устройстве
      received_at  TIMESTAMPTZ NOT NULL DEFAULT now() — время приёма сервером
      source       VARCHAR(20) NOT NULL DEFAULT 'browser'
      UNIQUE (user_id, recorded_at) — де-дуп повторно присланных точек
      INDEX (user_id, recorded_at) — "последняя точка каждого" / "трек за период"
      INDEX (recorded_at) — фоновая очистка записей старше 30 дней по всем пользователям

Revision ID: e2a4c6f8b0d2
Revises: c9d1e3f5a7b9
Create Date: 2026-09-04 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e2a4c6f8b0d2'
down_revision = 'c9d1e3f5a7b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table("staff_shifts"):
        op.create_table(
            "staff_shifts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
        op.create_index("ix_staff_shifts_user_id", "staff_shifts", ["user_id"])
        op.create_index(
            "uq_staff_shifts_active_user", "staff_shifts", ["user_id"],
            unique=True, postgresql_where=sa.text("is_active"),
        )

    if not insp.has_table("staff_location_points"):
        op.create_table(
            "staff_location_points",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("lat", sa.Float(), nullable=False),
            sa.Column("lon", sa.Float(), nullable=False),
            sa.Column("accuracy_m", sa.Float(), nullable=True),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.Column("source", sa.String(20), nullable=False, server_default="browser"),
            sa.UniqueConstraint("user_id", "recorded_at", name="uq_staff_location_user_recorded"),
        )
        op.create_index("ix_staff_location_points_user_id", "staff_location_points", ["user_id"])
        op.create_index(
            "ix_staff_location_points_user_recorded", "staff_location_points",
            ["user_id", "recorded_at"],
        )
        op.create_index(
            "ix_staff_location_points_recorded_at", "staff_location_points", ["recorded_at"],
        )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS staff_location_points"))
    op.execute(sa.text("DROP TABLE IF EXISTS staff_shifts"))
