"""add okpd2_codes table and seed from tsv

Revision ID: r5s6t7u8v9w0
Revises: q4r5s6t7u8v9
Create Date: 2026-07-28 00:00:00.000000

"""
import gzip
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = 'r5s6t7u8v9w0'
down_revision = 'q4r5s6t7u8v9'
branch_labels = None
depends_on = None

_TSV_PATH = Path(__file__).resolve().parents[2] / "app" / "data" / "okpd2.tsv.gz"
_CHUNK = 2000


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table("okpd2_codes"):
        op.create_table(
            "okpd2_codes",
            sa.Column("code", sa.String(20), primary_key=True),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("section", sa.String(2), nullable=True),
        )
        # Functional index on lower(name) for ILIKE searches
        op.execute(
            "CREATE INDEX ix_okpd2_codes_name_lower ON okpd2_codes (lower(name))"
        )

    # Seed only if table is empty
    result = conn.execute(sa.text("SELECT COUNT(*) FROM okpd2_codes"))
    count = result.scalar()
    if count and count > 0:
        return

    # Load data from gzip TSV
    # Format: code<TAB>name<TAB>section  — but name may contain stray tabs.
    # Strategy: first field = code, last field = section candidate (only if
    # its length <= 2), everything in-between = name (joined with space).
    import re
    rows = []
    with gzip.open(str(_TSV_PATH), "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            code = parts[0].strip()[:20]  # clamp to column width
            if not code:
                continue

            # Determine section from the last field when unambiguous
            last = parts[-1].strip() if len(parts) > 1 else ""
            if len(parts) >= 3 and len(last) <= 2:
                # last field is a valid section code; name is everything between
                section = last if last else None
                name_parts = parts[1:-1]
            else:
                # last field is not a section (too long or only 2 fields total)
                section = None
                name_parts = parts[1:]

            # Join fragments, normalise whitespace
            raw_name = " ".join(name_parts)
            name = re.sub(r"[ \t]+", " ", raw_name).strip()
            if not name:
                continue

            rows.append({
                "code": code,
                "name": name,
                "section": section,
            })

    # Bulk insert in chunks
    okpd2_table = sa.table(
        "okpd2_codes",
        sa.column("code", sa.String),
        sa.column("name", sa.Text),
        sa.column("section", sa.String),
    )
    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i: i + _CHUNK]
        op.bulk_insert(okpd2_table, chunk)


def downgrade():
    op.drop_table("okpd2_codes")
