"""Разовый запрос местоположения через мессенджер — staff_location_requests

Владелец (организация спасателей, 2026-09): у 32 из 41 сотрудников нет
привязанного мессенджера, а от остальных нельзя дождаться, что они сами
включат смену. Диспетчер нажимает «Запросить местоположение» у конкретного
человека — уходит сообщение с кнопкой отправки геопозиции (Telegram) или
текстовая просьба (MAX — см. app/services/staff_location_requests.py, почему
кнопка не реализована для MAX). Разово, не постоянная трансляция.

Создаёт (идемпотентно, под inspector.has_table() guard, по образцу
e2a4c6f8b0d2_staff_location_tracking.py):

  - staff_location_requests:
      requested_by_id  FK users(id) ON DELETE CASCADE, NOT NULL — кто запросил
      user_id          FK users(id) ON DELETE CASCADE, NOT NULL — у кого
      status           VARCHAR(20) NOT NULL DEFAULT 'sent'
                        sent | answered | expired | cancelled
      channels_sent    VARCHAR(40) NULL — "telegram", "max" или "telegram,max"
      created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
      expires_at       TIMESTAMPTZ NOT NULL — created_at + TTL (30 мин, см. сервис)
      responded_at     TIMESTAMPTZ NULL
      point_id         FK staff_location_points(id) ON DELETE SET NULL, NULL
      INDEX (user_id, status)  — "есть ли активный запрос у пользователя"
      INDEX (created_at)       — список запросов диспетчера, недавние сверху

Revision ID: r4t6v8x0z2b4
Revises: e2a4c6f8b0d2
Create Date: 2026-09-04 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'r4t6v8x0z2b4'
down_revision = 'e2a4c6f8b0d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table("staff_location_requests"):
        op.create_table(
            "staff_location_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("requested_by_id", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="sent"),
            sa.Column("channels_sent", sa.String(40), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("point_id", sa.Integer(),
                      sa.ForeignKey("staff_location_points.id", ondelete="SET NULL"), nullable=True),
        )
        op.create_index(
            "ix_staff_location_requests_requested_by_id", "staff_location_requests", ["requested_by_id"],
        )
        op.create_index(
            "ix_staff_location_requests_user_id", "staff_location_requests", ["user_id"],
        )
        op.create_index(
            "ix_staff_location_requests_user_status", "staff_location_requests", ["user_id", "status"],
        )
        op.create_index(
            "ix_staff_location_requests_created_at", "staff_location_requests", ["created_at"],
        )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS staff_location_requests"))
