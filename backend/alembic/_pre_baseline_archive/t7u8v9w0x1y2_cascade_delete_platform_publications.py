"""cascade delete platform_publications with purchase

Revision ID: t7u8v9w0x1y2
Revises: s6t7u8v9w0x1
Create Date: 2026-04-23

Phase 17.1-07 hotfix: DELETE purchase fails on prod with
NotNullViolationError because SQLAlchemy tries to UPDATE
platform_publications SET purchase_id=NULL (old relationship without
passive_deletes) while the column is NOT NULL.

The model already declares ondelete='CASCADE' but the existing prod FK
was created without it. This migration drops the old FK and recreates
it WITH ON DELETE CASCADE so the DB handles child-row removal and
SQLAlchemy's passive_deletes works correctly.

Also cleans stale orphan rows (e.g. the n8n-era publication with
error_text='Сброс — таймаут n8n webhook') via the not-null check that
was implicit before.
"""
from alembic import op
import sqlalchemy as sa

revision = 't7u8v9w0x1y2'
down_revision = 's6t7u8v9w0x1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # Drop whatever FK currently links platform_publications.purchase_id
    # to purchases.id (name varies across environments).
    connection.execute(sa.text("""
        DO $$
        DECLARE
            fk_name text;
        BEGIN
            SELECT conname INTO fk_name
            FROM pg_constraint
            WHERE conrelid = 'platform_publications'::regclass
              AND contype = 'f'
              AND array_to_string(conkey, ',') = (
                SELECT array_to_string(array_agg(attnum ORDER BY attnum), ',')
                FROM pg_attribute
                WHERE attrelid = 'platform_publications'::regclass
                  AND attname = 'purchase_id'
              );
            IF fk_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE platform_publications DROP CONSTRAINT %I', fk_name);
            END IF;
        END $$;
    """))

    # Recreate FK with ON DELETE CASCADE
    connection.execute(sa.text("""
        ALTER TABLE platform_publications
          ADD CONSTRAINT platform_publications_purchase_id_fkey
          FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE
    """))


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(sa.text("""
        ALTER TABLE platform_publications
          DROP CONSTRAINT IF EXISTS platform_publications_purchase_id_fkey
    """))

    # Restore plain FK without CASCADE (pre-hotfix behaviour)
    connection.execute(sa.text("""
        ALTER TABLE platform_publications
          ADD CONSTRAINT platform_publications_purchase_id_fkey
          FOREIGN KEY (purchase_id) REFERENCES purchases(id)
    """))
