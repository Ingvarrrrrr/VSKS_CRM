"""reconcile FK ON DELETE rules with models

Revision ID: b7e1c2d3f4a5
Revises: 77a79dee6f2f
Create Date: 2026-06-02 14:45:00.000000

The models declare ondelete=CASCADE/SET NULL on a set of foreign keys, but the
prod DB was built by the old runtime-DDL path which created those FKs WITHOUT
the ondelete rule (and the baseline was *stamped* on prod, not run, so create_all
never re-asserted them). This migration reconciles each FK to its declared
ondelete.

Safety: each FK is reconciled via a DO block that (1) finds the *existing*
constraint on that table+column by introspection — so it is agnostic to whatever
name prod actually gave it — then (2) drops and recreates it with the canonical
name and the desired ON DELETE. The recreate fires ONLY if a constraint was
found, so we never add a brand-new FK that could fail validation against orphan
rows on prod. FKs already enforced satisfy their data, so drop+recreate (changing
only the ondelete) re-validates cleanly. Idempotent.
"""
from alembic import op

revision = 'b7e1c2d3f4a5'
down_revision = '77a79dee6f2f'
branch_labels = None
depends_on = None

# (table, column, ref_table, on_delete)
_FKS = [
    ("contracts", "subsidy_id", "subsidies", "SET NULL"),
    ("contract_subsidies", "contract_id", "contracts", "CASCADE"),
    ("contract_subsidies", "subsidy_id", "subsidies", "CASCADE"),
    ("feo_categories", "parent_id", "feo_categories", "CASCADE"),
    ("feo_categories", "subsidy_id", "subsidies", "CASCADE"),
    ("products", "feo_category_id", "feo_categories", "SET NULL"),
    ("products", "org_id", "organizations", "CASCADE"),
    ("purchases", "feo_category_id", "feo_categories", "SET NULL"),
    ("purchases", "subsidy_id", "subsidies", "SET NULL"),
    ("purchases", "service_note_to_user_id", "users", "SET NULL"),
    ("purchases", "vehicle_id", "vehicles", "SET NULL"),
    ("purchase_subsidy_allocations", "purchase_id", "purchases", "CASCADE"),
    ("purchase_subsidy_allocations", "subsidy_id", "subsidies", "CASCADE"),
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
    for table, col, ref, on_delete in _FKS:
        op.execute(_reconcile(table, col, ref, on_delete))


def downgrade() -> None:
    # Restore plain FKs (no ON DELETE) for the same set.
    for table, col, ref, _ in _FKS:
        op.execute(_reconcile(table, col, ref, None))
