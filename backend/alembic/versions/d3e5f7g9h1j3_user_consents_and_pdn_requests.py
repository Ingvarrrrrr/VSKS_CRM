"""152-ФЗ: user_consents + personal_data_requests

Владелец (2026-09-16): приведение сервиса в соответствие с 152-ФЗ — согласие
на обработку ПДн фиксируется при регистрации (см.
backend/app/routers/organizations.py:register()), обращения субъектов ПДн —
через новый роутер backend/app/routers/legal.py.

Идемпотентно — inspector-guard на create_table, т.к. на старте контейнера
гонится `alembic upgrade head`, а рядом check_schema делает create_all для
новых таблиц (конфликт DDL иначе валит бэкенд в 502, см. соседние миграции).

Revision ID: d3e5f7g9h1j3
Revises: e4f6a8b0c2d4
Create Date: 2026-09-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd3e5f7g9h1j3'
down_revision = 'e4f6a8b0c2d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("user_consents"):
        op.create_table(
            "user_consents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("document_version", sa.String(255), nullable=False),
            sa.Column("documents", postgresql.JSONB(), nullable=False),
            sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("source", sa.String(50), nullable=False, server_default="registration"),
            sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("withdrawal_reason", sa.Text(), nullable=True),
        )
        op.create_index("ix_user_consents_user_id", "user_consents", ["user_id"])
        op.create_index("ix_user_consents_email", "user_consents", ["email"])

    if not insp.has_table("personal_data_requests"):
        op.create_table(
            "personal_data_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("requester_name", sa.String(255), nullable=True),
            sa.Column("reply_contact", sa.String(255), nullable=False),
            sa.Column("request_type", sa.String(20), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="new"),
            sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("response_text", sa.Text(), nullable=True),
            sa.Column("handled_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )
        op.create_index("ix_personal_data_requests_user_id", "personal_data_requests", ["user_id"])


def downgrade() -> None:
    op.drop_table("personal_data_requests")
    op.drop_table("user_consents")
