"""add signatory structured parts (last/first/middle name + position) to contractors, organizations, subsidy_contractor_overrides

Revision ID: p3q4r5s6t7u8
Revises: o2p3q4r5s6t7
Create Date: 2026-07-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'p3q4r5s6t7u8'
down_revision = 'o2p3q4r5s6t7'
branch_labels = None
depends_on = None


def split_position_and_fio(raw, position=None):
    """Parse a raw signatory string into (last, first, middle, position).

    Rules:
    - empty/None raw → (None, None, None, position or None)
    - position given → parse raw as FIO only
    - ':' in raw → left side = position, right side = FIO
    - >3 words, no ':' → first (n-3) words = position, last 3 = FIO
    - exactly 3 words → all FIO, position None
    - 2 words → last/first, middle None, position None
    - 1 word → last only
    FIO split: 3+ words → (w[0], w[1], joined rest); 2 → (w[0], w[1], None); 1 → (w[0], None, None)
    """
    if not raw or not raw.strip():
        return (None, None, None, position or None)
    raw = raw.strip()
    if position:
        words = raw.split()
        if len(words) >= 3:
            return (words[0], words[1], ' '.join(words[2:]), position)
        if len(words) == 2:
            return (words[0], words[1], None, position)
        return (words[0], None, None, position)
    if ':' in raw:
        pos_part, fio_part = raw.split(':', 1)
        words = fio_part.strip().split()
        if len(words) >= 3:
            return (words[0], words[1], ' '.join(words[2:]), pos_part.strip() or None)
        if len(words) == 2:
            return (words[0], words[1], None, pos_part.strip() or None)
        if words:
            return (words[0], None, None, pos_part.strip() or None)
        return (None, None, None, pos_part.strip() or None)
    words = raw.split()
    if len(words) > 3:
        pos_str = ' '.join(words[:-3])
        return (words[-3], words[-2], words[-1], pos_str or None)
    if len(words) == 3:
        return (words[0], words[1], words[2], None)
    if len(words) == 2:
        return (words[0], words[1], None, None)
    return (words[0], None, None, None)


def _add_col(conn, insp, table, col_name, col_def):
    """Add column if it does not already exist (idempotent)."""
    existing = {c['name'] for c in insp.get_columns(table)}
    if col_name not in existing:
        op.add_column(table, sa.Column(col_name, col_def, nullable=True))


def _backfill_table(conn, table):
    """Backfill signatory parts for a single table."""
    rows = conn.execute(sa.text(
        f"SELECT id, signatory, signatory_position FROM {table} "
        f"WHERE signatory IS NOT NULL AND signatory != '' "
        f"AND signatory_last_name IS NULL"
    )).fetchall()
    for row in rows:
        last, first, middle, pos = split_position_and_fio(row[1], row[2])
        if pos and not row[2]:
            conn.execute(sa.text(
                f"UPDATE {table} SET "
                f"signatory_last_name = :last, "
                f"signatory_first_name = :first, "
                f"signatory_middle_name = :middle, "
                f"signatory_position = :pos "
                f"WHERE id = :id"
            ), {"last": last, "first": first, "middle": middle, "pos": pos, "id": row[0]})
        else:
            conn.execute(sa.text(
                f"UPDATE {table} SET "
                f"signatory_last_name = :last, "
                f"signatory_first_name = :first, "
                f"signatory_middle_name = :middle "
                f"WHERE id = :id"
            ), {"last": last, "first": first, "middle": middle, "id": row[0]})


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # Tables are checked before DDL/DML because migrations run automatically at container start
    # and a missing table would raise an exception and crash the application.
    existing_tables = set(insp.get_table_names())

    # ── contractors ──────────────────────────────────────────────────────────
    if 'contractors' in existing_tables:
        for col in ('signatory_last_name', 'signatory_first_name', 'signatory_middle_name'):
            _add_col(conn, insp, 'contractors', col, sa.String(100))
        _backfill_table(conn, 'contractors')

    # ── organizations ────────────────────────────────────────────────────────
    if 'organizations' in existing_tables:
        _add_col(conn, insp, 'organizations', 'signatory_position', sa.String(255))
        for col in ('signatory_last_name', 'signatory_first_name', 'signatory_middle_name'):
            _add_col(conn, insp, 'organizations', col, sa.String(100))
        _backfill_table(conn, 'organizations')

    # ── subsidy_contractor_overrides ─────────────────────────────────────────
    if 'subsidy_contractor_overrides' in existing_tables:
        _add_col(conn, insp, 'subsidy_contractor_overrides', 'signatory_position', sa.String(255))
        for col in ('signatory_last_name', 'signatory_first_name', 'signatory_middle_name'):
            _add_col(conn, insp, 'subsidy_contractor_overrides', col, sa.String(100))
        _backfill_table(conn, 'subsidy_contractor_overrides')


def downgrade():
    for col in ('signatory_last_name', 'signatory_first_name', 'signatory_middle_name'):
        op.drop_column('contractors', col)

    op.drop_column('organizations', 'signatory_position')
    for col in ('signatory_last_name', 'signatory_first_name', 'signatory_middle_name'):
        op.drop_column('organizations', col)

    op.drop_column('subsidy_contractor_overrides', 'signatory_position')
    for col in ('signatory_last_name', 'signatory_first_name', 'signatory_middle_name'):
        op.drop_column('subsidy_contractor_overrides', col)
