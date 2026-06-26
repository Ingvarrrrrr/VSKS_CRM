"""migrate department_members to user_organizations + add hired_at

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-25 12:00:00.000000

Migration plan:
1. Add hired_at column to user_organizations
2. Backfill hired_at on UO rows that already match a DM row (by user+dept)
3. Insert orphan DM rows that have no matching UO row
4. Drop department_members table
"""
import sqlalchemy as sa
from alembic import op

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Add hired_at column
    op.add_column(
        'user_organizations',
        sa.Column('hired_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    )

    # Step 2: Backfill hired_at on existing matched UO rows from DM.created_at
    op.execute(sa.text(
        """
        UPDATE user_organizations uo
        SET hired_at = dm.created_at
        FROM department_members dm
        WHERE uo.user_id = dm.user_id
          AND uo.dept_id = dm.department_id
          AND uo.hired_at IS NULL
        """
    ))

    # Step 3: Insert orphan DM rows that have no matching UO row
    op.execute(sa.text(
        """
        INSERT INTO user_organizations (user_id, org_id, dept_id, position, hired_at)
        SELECT dm.user_id, d.org_id, dm.department_id, dm.position, dm.created_at
        FROM department_members dm
        JOIN departments d ON d.id = dm.department_id
        LEFT JOIN user_organizations uo
          ON uo.user_id = dm.user_id AND uo.dept_id = dm.department_id
        WHERE uo.id IS NULL
        """
    ))

    # Step 4: Drop department_members table (now superseded by user_organizations)
    op.drop_table('department_members')


def downgrade() -> None:
    # Recreate department_members (best-effort — data may differ from original)
    op.create_table(
        'department_members',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.String(300), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.UniqueConstraint('department_id', 'user_id', name='uq_dept_user'),
    )

    # Backfill from user_organizations rows that have a dept_id
    op.execute(sa.text(
        """
        INSERT INTO department_members (department_id, user_id, position, created_at)
        SELECT uo.dept_id, uo.user_id, uo.position, COALESCE(uo.hired_at, now())
        FROM user_organizations uo
        WHERE uo.dept_id IS NOT NULL
        ON CONFLICT (department_id, user_id) DO NOTHING
        """
    ))

    # Drop hired_at column
    op.drop_column('user_organizations', 'hired_at')
