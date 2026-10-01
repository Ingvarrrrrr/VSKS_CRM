"""Корректировка утверждённой субсидии через проверку, волна 1: subsidy_revisions/subsidy_revision_ops

Владелец: субсидию в статусе 'approved' правят либо напрямую (право
subsidy.edit), либо через корректировку (новое право subsidy.correct) —
правки ждут проверки. Модели — app/models/subsidy_revision.py
(SubsidyRevision/SubsidyRevisionOp), докстринг там разбирает все поля.
Пока функция не принята, поведение спрятано за env-флагом
SUBSIDY_REVISION_ENABLED (см. app/services/subsidy_revision_guard.py) —
эта миграция лишь заводит таблицы, ничего не меняет в существующем поведении.

Идемпотентно — inspector-guard на create_table/create_index, т.к. на старте
контейнера гонится `alembic upgrade head`, а рядом check_schema делает
create_all для новых таблиц (см. соседние миграции, например t6v8x1z3b5d7).

down_revision указывает на последнюю ЗАКОММИЧЕННУЮ голову (w7x8y9z0a1b2).
В рабочем дереве есть незакоммиченные чужие головы (d3e5f7g9h1j3,
x8y9z0a1b2c3) — эта миграция на них сознательно НЕ ссылается и их не трогает;
слияние веток — отдельная задача после того, как все параллельные волны
закоммичены.

Revision ID: a1b3c5d7e9f1
Revises: w7x8y9z0a1b2
Create Date: 2026-10-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a1b3c5d7e9f1'
down_revision = 'w7x8y9z0a1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("subsidy_revisions"):
        op.create_table(
            "subsidy_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("subsidy_id", sa.Integer(), sa.ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("number", sa.Integer(), nullable=False),
            sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("author_comment", sa.Text(), nullable=True),
            sa.Column("reviewer_comment", sa.Text(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    existing_indexes = (
        {ix["name"] for ix in insp.get_indexes("subsidy_revisions")}
        if insp.has_table("subsidy_revisions") else set()
    )
    if "ix_subsidy_revisions_subsidy_id" not in existing_indexes:
        op.create_index("ix_subsidy_revisions_subsidy_id", "subsidy_revisions", ["subsidy_id"])
    if "ux_subsidy_revisions_one_open_per_author" not in existing_indexes:
        op.create_index(
            "ux_subsidy_revisions_one_open_per_author",
            "subsidy_revisions",
            ["subsidy_id", "author_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('draft', 'submitted', 'partially_decided')"),
        )

    if not insp.has_table("subsidy_revision_ops"):
        op.create_table(
            "subsidy_revision_ops",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("revision_id", sa.Integer(), sa.ForeignKey("subsidy_revisions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("op_type", sa.String(20), nullable=False),
            sa.Column("entity_type", sa.String(20), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=True),
            sa.Column("target_ref", sa.String(40), nullable=True),
            sa.Column("parent_ref", sa.String(40), nullable=True),
            sa.Column("depends_on_op_id", sa.Integer(), sa.ForeignKey("subsidy_revision_ops.id", ondelete="CASCADE"), nullable=True),
            sa.Column("field_group", sa.String(60), nullable=True),
            sa.Column("before", postgresql.JSONB(), nullable=True),
            sa.Column("after", postgresql.JSONB(), nullable=True),
            sa.Column("reviewer_after", postgresql.JSONB(), nullable=True),
            sa.Column("added_by_reviewer", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("bundle_no", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("review_comment", sa.Text(), nullable=True),
            sa.Column("applied_entity_id", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    existing_op_indexes = (
        {ix["name"] for ix in insp.get_indexes("subsidy_revision_ops")}
        if insp.has_table("subsidy_revision_ops") else set()
    )
    if "ix_subsidy_revision_ops_revision_id" not in existing_op_indexes:
        op.create_index("ix_subsidy_revision_ops_revision_id", "subsidy_revision_ops", ["revision_id"])


def downgrade() -> None:
    op.drop_table("subsidy_revision_ops")
    op.drop_table("subsidy_revisions")
