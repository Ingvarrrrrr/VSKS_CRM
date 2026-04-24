"""add product photo bytea storage

Revision ID: u8v9w0x1y2z3
Revises: t7u8v9w0x1y2
Create Date: 2026-04-23

Phase 17.1-08: migrate product photos from filesystem to PostgreSQL bytea.

Rationale: the /app/uploads/products volume is unreliable — prod already lost
previously downloaded photos. One DB backup should restore all photos.

Columns added:
- photo_data  (BYTEA)       — binary content of the photo
- photo_mime  (VARCHAR(50)) — Content-Type for serving (image/jpeg, etc.)
- photo_size  (INTEGER)     — byte size, useful for admin panel / diagnostics

The existing `photo_url` column is KEPT intact. For products whose photo_url
holds an external marketplace URL, that URL remains the source of truth for
re-downloading; photo_data is a cached copy. No backfill is done here —
`POST /api/products/download-photos` will populate photo_data on demand.
"""
from alembic import op
import sqlalchemy as sa


revision = 'u8v9w0x1y2z3'
down_revision = 't7u8v9w0x1y2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'products',
        sa.Column('photo_data', sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        'products',
        sa.Column('photo_mime', sa.String(length=50), nullable=True),
    )
    op.add_column(
        'products',
        sa.Column('photo_size', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('products', 'photo_size')
    op.drop_column('products', 'photo_mime')
    op.drop_column('products', 'photo_data')
