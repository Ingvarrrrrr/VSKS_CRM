"""Черновые субсидии (владелец, план C1/C2): любой сотрудник может создать
субсидию-черновик и работать над ней вместе с приглашёнными участниками, но
в работу (закупки/заявки/договоры) она идёт только после утверждения
администратором. Один флаг состояния — никаких цепочек согласования.

Добавляет идемпотентно (guard через sa.inspect):
  subsidies:
    - status       VARCHAR(20) NOT NULL DEFAULT 'draft'
    - created_by   INTEGER FK users.id (SET NULL)
    - approved_by  INTEGER FK users.id (SET NULL)
    - approved_at  TIMESTAMPTZ NULL

Существующие субсидии (созданные до этой ревизии) переводятся в 'approved' —
они уже находятся в работе, черновиками их делать нельзя (иначе 22 живые
субсидии внезапно перестали бы быть доступны для новых закупок/заявок/договоров).

Новая таблица subsidy_members — калька wish_members (участники совместной
работы над черновиком): subsidy_id, user_id, added_by_id, created_at,
уникальность пары (subsidy_id, user_id).

Revision ID: 2b00d0245ba5
Revises: f25e7fa19cbc
Create Date: 2026-09-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '2b00d0245ba5'
down_revision = 'f25e7fa19cbc'
branch_labels = None
depends_on = None


def _cols(table: str) -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    existing = _cols('subsidies')

    if 'status' not in existing:
        op.add_column('subsidies', sa.Column(
            'status', sa.String(20), nullable=False, server_default='draft'
        ))
    if 'created_by' not in existing:
        op.add_column('subsidies', sa.Column(
            'created_by', sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True
        ))
    if 'approved_by' not in existing:
        op.add_column('subsidies', sa.Column(
            'approved_by', sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True
        ))
    if 'approved_at' not in existing:
        op.add_column('subsidies', sa.Column(
            'approved_at', sa.DateTime(timezone=True), nullable=True
        ))

    # Существующие субсидии — уже рабочие, не черновики (иначе 22 живые
    # субсидии внезапно перестали бы быть доступны для закупок/заявок/договоров).
    op.execute(sa.text("UPDATE subsidies SET status = 'approved' WHERE status = 'draft'"))

    if 'subsidy_members' not in insp.get_table_names():
        op.create_table(
            'subsidy_members',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('subsidy_id', sa.Integer(),
                      sa.ForeignKey('subsidies.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('user_id', sa.Integer(),
                      sa.ForeignKey('users.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('added_by_id', sa.Integer(),
                      sa.ForeignKey('users.id', ondelete='SET NULL'),
                      nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        )
        existing_idx = []
        existing_uq = []
    else:
        existing_idx = [ix['name'] for ix in insp.get_indexes('subsidy_members')]
        existing_uq = [uq['name'] for uq in insp.get_unique_constraints('subsidy_members')]

    if 'ix_subsidy_members_subsidy_id' not in existing_idx:
        op.create_index('ix_subsidy_members_subsidy_id', 'subsidy_members', ['subsidy_id'])
    if 'uq_subsidy_members_subsidy_user' not in existing_uq:
        op.create_unique_constraint(
            'uq_subsidy_members_subsidy_user', 'subsidy_members', ['subsidy_id', 'user_id']
        )


def downgrade():
    op.execute(sa.text('DROP TABLE IF EXISTS subsidy_members'))
    op.execute(sa.text('ALTER TABLE subsidies DROP COLUMN IF EXISTS approved_at'))
    op.execute(sa.text('ALTER TABLE subsidies DROP COLUMN IF EXISTS approved_by'))
    op.execute(sa.text('ALTER TABLE subsidies DROP COLUMN IF EXISTS created_by'))
    op.execute(sa.text('ALTER TABLE subsidies DROP COLUMN IF EXISTS status'))
