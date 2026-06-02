"""add missing purchases.service_note_to_user_id FK (SET NULL)

Revision ID: c9f2a3b4d5e6
Revises: b7e1c2d3f4a5
Create Date: 2026-06-02 15:05:00.000000

The model declares purchases.service_note_to_user_id with a FK to users
(ondelete SET NULL), but on prod the column was added by runtime-DDL WITHOUT a
FK constraint at all — so the previous reconcile migration (which only touches
existing FKs) correctly skipped it. This adds the missing FK.

create-if-missing: the DO block only adds the constraint when none exists on that
column, so it is a no-op on localhost (where the FK already exists) and creates it
on prod. Verified 0 orphan rows on prod before writing this, so ADD CONSTRAINT
validates cleanly.
"""
from alembic import op

revision = 'c9f2a3b4d5e6'
down_revision = 'b7e1c2d3f4a5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
DO $$
DECLARE cname text;
BEGIN
    SELECT con.conname INTO cname
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = con.conkey[1]
    WHERE con.contype = 'f' AND rel.relname = 'purchases'
      AND a.attname = 'service_note_to_user_id';
    IF cname IS NULL THEN
        UPDATE purchases SET service_note_to_user_id = NULL
        WHERE service_note_to_user_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = service_note_to_user_id);
        ALTER TABLE purchases
            ADD CONSTRAINT purchases_service_note_to_user_id_fkey
            FOREIGN KEY (service_note_to_user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;
"""
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_service_note_to_user_id_fkey"
    )
