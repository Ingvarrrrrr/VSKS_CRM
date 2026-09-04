"""Редактор значков кузова ТС — переопределения по организации

Владелец (2026-09): «Я тебя просил показать лист, как сопоставлен какой
кузов — картинка, и чтобы я мог это корректировать». Хранение сопоставления
«кузов → значок» переносится из хардкода (frontend bodyTypeIcon.ts) в БД —
но ТОЛЬКО переопределения: хардкод остаётся значением по умолчанию, если
переопределения для (org_id, body_type) нет.

Создаёт (идемпотентно, под inspector.has_table() guard, по образцу
p9r2t5v8x1z4_price_freshness_and_history.py):
  - body_type_icon_overrides:
      org_id      FK organizations(id) ON DELETE CASCADE, NOT NULL
      body_type   VARCHAR(100) NOT NULL — значение поля «Кузов» (BODY_TYPE_OPTIONS)
      icon_kind   VARCHAR(10)  NOT NULL — 'img' | 'mdi'
      icon_value  VARCHAR(100) NOT NULL — PNG basename либо полное имя mdi-иконки
      updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
      UNIQUE (org_id, body_type)

Revision ID: c9d1e3f5a7b9
Revises: a2b4c6d8e0f2
Create Date: 2026-09-04 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d1e3f5a7b9'
down_revision = 'a2b4c6d8e0f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table("body_type_icon_overrides"):
        op.create_table(
            "body_type_icon_overrides",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("org_id", sa.Integer(),
                      sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("body_type", sa.String(100), nullable=False),
            sa.Column("icon_kind", sa.String(10), nullable=False),
            sa.Column("icon_value", sa.String(100), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint("org_id", "body_type", name="uq_body_type_icon_org_body"),
        )
        op.create_index(
            "ix_body_type_icon_overrides_org_id", "body_type_icon_overrides", ["org_id"]
        )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS body_type_icon_overrides"))
