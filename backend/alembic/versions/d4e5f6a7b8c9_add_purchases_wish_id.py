"""add purchases.wish_id (link purchase back to source wish)

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-06-07 12:00:00.000000

Распределённая заявка (wish) переходит в status='converted' и линкует свои
закупки через purchases.wish_id. Нужно для дедупа (не плодить закупки при
повторном распределении) и для фильтрации «Заявки» = в работе, «Закупки» =
распределённые.

create-if-missing: добавляем колонку и FK (ON DELETE SET NULL) только если их
ещё нет — no-op на средах, где колонка уже появилась.
"""
from alembic import op

revision = 'd4e5f6a7b8c9'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
DO $$
DECLARE cname text;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'purchases' AND column_name = 'wish_id'
    ) THEN
        ALTER TABLE purchases ADD COLUMN wish_id INTEGER;
    END IF;

    SELECT con.conname INTO cname
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = con.conkey[1]
    WHERE con.contype = 'f' AND rel.relname = 'purchases'
      AND a.attname = 'wish_id';
    IF cname IS NULL THEN
        ALTER TABLE purchases
            ADD CONSTRAINT purchases_wish_id_fkey
            FOREIGN KEY (wish_id) REFERENCES wishes(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'purchases' AND indexname = 'ix_purchases_wish_id'
    ) THEN
        CREATE INDEX ix_purchases_wish_id ON purchases (wish_id);
    END IF;
END $$;
"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_purchases_wish_id")
    op.execute("ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_wish_id_fkey")
    op.execute("ALTER TABLE purchases DROP COLUMN IF EXISTS wish_id")
