"""backfill user_org_access from users.org_id + user_organizations

Revision ID: s6t7u8v9w0x1
Revises: r5s6t7u8v9w0
Create Date: 2026-04-23

Phase 17.1-05: historical user_org_access rows are missing because earlier
user CRUD and multi-org membership CRUD did not populate the table. This
migration backfills:
  1. Primary org membership — one row per user with users.org_id NOT NULL
  2. Extra org membership — one row per user_organizations entry

All inserts are idempotent via ON CONFLICT (user_id, org_id) DO NOTHING.
Role defaults to the user's global role (user.role) so existing callers keep
current behaviour until an admin explicitly sets a per-org role.
"""
from alembic import op
import sqlalchemy as sa

revision = 's6t7u8v9w0x1'
down_revision = 'r5s6t7u8v9w0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # Backfill 1: primary org from users.org_id
    connection.execute(sa.text("""
        INSERT INTO user_org_access (user_id, org_id, role)
        SELECT id, org_id, role
        FROM users
        WHERE org_id IS NOT NULL
        ON CONFLICT (user_id, org_id) DO NOTHING
    """))

    # Backfill 2: extra orgs from user_organizations (role mirrors user.role)
    connection.execute(sa.text("""
        INSERT INTO user_org_access (user_id, org_id, role)
        SELECT uo.user_id, uo.org_id, u.role
        FROM user_organizations uo
        JOIN users u ON u.id = uo.user_id
        ON CONFLICT (user_id, org_id) DO NOTHING
    """))


def downgrade() -> None:
    # No-op: we cannot safely distinguish backfilled rows from manually-created
    # ones. Leaving uoa rows in place on downgrade is harmless because callers
    # fall back to user.role when uoa.role is NULL or row missing.
    pass
