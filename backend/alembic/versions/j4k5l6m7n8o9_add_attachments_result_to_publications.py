"""platform_publications: add attachments_result column

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-07-21 00:00:00.000000
"""
from alembic import op
from sqlalchemy import text


revision = 'j4k5l6m7n8o9'
down_revision = 'i3j4k5l6m7n8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text(
        "ALTER TABLE platform_publications ADD COLUMN IF NOT EXISTS attachments_result TEXT"
    ))


def downgrade() -> None:
    op.execute(text(
        "ALTER TABLE platform_publications DROP COLUMN IF EXISTS attachments_result"
    ))
