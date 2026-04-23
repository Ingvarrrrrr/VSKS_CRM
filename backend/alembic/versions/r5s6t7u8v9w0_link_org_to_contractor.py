"""link organizations to contractors via FK + backfill by INN

Revision ID: r5s6t7u8v9w0
Revises: q4r5s6t7u8v9
Create Date: 2026-04-23

Makes Organization a thin reference to Contractor (single source of truth for legal requisites).
- Adds organizations.contractor_id (nullable FK, ON DELETE SET NULL)
- Indexes it
- Backfills by matching INN between organizations and contractors
"""
from alembic import op
import sqlalchemy as sa

revision = 'r5s6t7u8v9w0'
down_revision = 'q4r5s6t7u8v9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step A — add nullable FK column (no-op if already present)
    connection = op.get_bind()
    exists = connection.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='organizations' AND column_name='contractor_id'"
    )).scalar()
    if not exists:
        op.add_column(
            'organizations',
            sa.Column(
                'contractor_id',
                sa.Integer(),
                sa.ForeignKey('contractors.id', ondelete='SET NULL'),
                nullable=True,
            ),
        )
        op.create_index(
            'ix_organizations_contractor_id',
            'organizations',
            ['contractor_id'],
        )

    # Step B — backfill by INN match (idempotent — only fills NULL contractor_id)
    connection.execute(sa.text("""
        UPDATE organizations o
        SET contractor_id = c.id
        FROM contractors c
        WHERE o.contractor_id IS NULL
          AND o.inn IS NOT NULL
          AND o.inn <> ''
          AND c.inn = o.inn
    """))


def downgrade() -> None:
    op.drop_index('ix_organizations_contractor_id', table_name='organizations')
    op.drop_column('organizations', 'contractor_id')
