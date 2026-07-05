"""user FK ondelete SET NULL / CASCADE for safe user deletion

Revision ID: a5b6c7d8e9f0
Revises: c3d4e5f6a7b8
Create Date: 2026-07-06 00:00:00.000000

All FK columns that reference users.id currently lack an ON DELETE rule, which
means Postgres uses NO ACTION / RESTRICT and blocks deletion of a user who is
still referenced as an assignee/author/commenter anywhere.

This migration reconciles each FK using the same idempotent DO-block pattern as
b7e1c2d3f4a5: find the existing constraint by table+column introspection (name-
agnostic), drop it, re-add with the canonical name and the desired ON DELETE.

SET NULL  — executor/author fields (user gone → field becomes NULL)
CASCADE   — comment ownership (comment is meaningless without its author)

Additionally, columns that were NOT NULL but need SET NULL are relaxed first with
an idempotent ALTER COLUMN … DROP NOT NULL (safe to re-run on a column already
nullable).
"""
from alembic import op

revision = 'a5b6c7d8e9f0'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None

# (table, column, ref_table, on_delete)
# Columns marked with needs_drop_not_null=True had nullable=False in prod DDL and
# must be relaxed before the FK reconciliation so the SET NULL rule is valid.
_FKS = [
    # table                  column               ref_table  on_delete    drop_not_null
    ("tasks",                "assigned_user_id",  "users",   "SET NULL",  False),
    ("tasks",                "created_by_id",     "users",   "SET NULL",  True),
    ("purchases",            "assigned_user_id",  "users",   "SET NULL",  False),
    ("purchases",            "service_note_by",   "users",   "SET NULL",  False),
    ("bank_statement_imports", "uploaded_by_id",  "users",   "SET NULL",  False),
    ("commercial_requests",  "created_by",        "users",   "SET NULL",  False),
    ("report_configs",       "created_by_id",     "users",   "SET NULL",  False),
    ("purchase_comments",    "user_id",           "users",   "CASCADE",   False),
    ("task_comments",        "user_id",           "users",   "CASCADE",   False),
    # Extra FKs found by grep that also block user deletion:
    ("system_incidents",     "user_id",           "users",   "SET NULL",  False),
    ("wishes",               "created_by",        "users",   "SET NULL",  True),
    ("wishes",               "approved_by",       "users",   "SET NULL",  False),
]


def _reconcile(table: str, col: str, ref: str, on_delete: str | None) -> str:
    canonical = f"{table}_{col}_fkey"
    add_clause = (
        f"ALTER TABLE {table} ADD CONSTRAINT {canonical} "
        f"FOREIGN KEY ({col}) REFERENCES {ref}(id)"
    )
    if on_delete:
        add_clause += f" ON DELETE {on_delete}"
    return f"""
DO $$
DECLARE cname text;
BEGIN
    SELECT con.conname INTO cname
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = con.conkey[1]
    WHERE con.contype = 'f' AND rel.relname = '{table}' AND a.attname = '{col}';
    IF cname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', cname);
        {add_clause};
    END IF;
END $$;
"""


def upgrade() -> None:
    for table, col, ref, on_delete, drop_nn in _FKS:
        if drop_nn:
            # Idempotent: DROP NOT NULL on an already-nullable column is a no-op in Postgres.
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} DROP NOT NULL;")
        op.execute(_reconcile(table, col, ref, on_delete))


def downgrade() -> None:
    # Restore plain FKs (no ON DELETE) for the same set.
    # NOTE: does NOT restore NOT NULL constraints — that would require a data scan.
    for table, col, ref, _, _drop_nn in _FKS:
        op.execute(_reconcile(table, col, ref, None))
