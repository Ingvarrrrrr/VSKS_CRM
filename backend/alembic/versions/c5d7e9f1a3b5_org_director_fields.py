"""add director_* fields (ЕГРЮЛ head, separate from signatory) to organizations

Revision ID: c5d7e9f1a3b5
Revises: b3d5f7h9j1l3
Create Date: 2026-09-29 00:00:00.000000

Владелец (2026-09-29): «подписант может быть по доверенности — руководитель
организации это руководитель организации, из налоговой по ИНН». signatory_*
смешивало обе сущности (contractors_lookup.py клало директора из ЕГРЮЛ прямо
в signatory_*). Новые колонки хранят ИМЕННО директора по ЕГРЮЛ, отдельно от
подписанта. Данные НЕ копируются из signatory_* здесь — подписант мог быть
задан вручную как доверенное лицо, и это не то же самое.
"""
from alembic import op
import sqlalchemy as sa

revision = 'c5d7e9f1a3b5'
down_revision = 'b3d5f7h9j1l3'
branch_labels = None
depends_on = None


def _add_col(conn, insp, table, col_name, col_def):
    existing = {c['name'] for c in insp.get_columns(table)}
    if col_name not in existing:
        op.add_column(table, sa.Column(col_name, col_def, nullable=True))


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if 'organizations' not in set(insp.get_table_names()):
        return
    _add_col(conn, insp, 'organizations', 'director_last_name', sa.String(100))
    _add_col(conn, insp, 'organizations', 'director_first_name', sa.String(100))
    _add_col(conn, insp, 'organizations', 'director_middle_name', sa.String(100))
    _add_col(conn, insp, 'organizations', 'director_position', sa.String(255))


def downgrade():
    for col in ('director_last_name', 'director_first_name', 'director_middle_name', 'director_position'):
        op.drop_column('organizations', col)
