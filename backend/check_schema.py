#!/usr/bin/env python3
"""
Schema drift detector for VSKS CRM.

Usage (inside container):
    python /app/check_schema.py            # check only, exit 1 if drift
    python /app/check_schema.py --apply    # auto-apply ALTER TABLE statements

Run as part of EVERY backend deploy, BEFORE docker restart:
    docker exec vsks-crm-backend-1 python /app/check_schema.py --apply
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import all models so Base.metadata is fully populated
from app.database import Base, engine  # noqa
import app.models  # noqa — registers all tables via __init__.py

# Also import models not in __init__.py
try:
    from app.models.org_section_config import OrgSectionConfig  # noqa
except ImportError:
    pass
try:
    from app.models.delivery_address import DeliveryAddress  # noqa
except ImportError:
    pass

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import (
    Integer, BigInteger, SmallInteger,
    String, Text, Unicode, UnicodeText,
    Boolean,
    Numeric, Float, Double,
    Date, DateTime, Time,
    LargeBinary,
    Enum,
)


def _sqlalchemy_type_to_pg(col_type) -> str:
    """Convert a SQLAlchemy column type to a PostgreSQL type string."""
    type_class = type(col_type)
    type_name = type_class.__name__.upper()

    # JSONB (PostgreSQL dialect)
    if hasattr(col_type, '__class__') and col_type.__class__.__name__ == 'JSONB':
        return 'JSONB'

    # Integer variants
    if type_class in (Integer,) or type_name in ('INTEGER', 'INT'):
        return 'INTEGER'
    if type_class in (BigInteger,) or type_name == 'BIGINTEGER':
        return 'BIGINT'
    if type_class in (SmallInteger,) or type_name == 'SMALLINTEGER':
        return 'SMALLINT'

    # String variants
    if type_class in (String, Unicode) or type_name in ('STRING', 'VARCHAR'):
        length = getattr(col_type, 'length', None)
        return f'VARCHAR({length})' if length else 'TEXT'
    if type_class in (Text, UnicodeText) or type_name in ('TEXT',):
        return 'TEXT'

    # Boolean
    if type_class in (Boolean,) or type_name == 'BOOLEAN':
        return 'BOOLEAN'

    # Numeric / Float
    if type_class in (Numeric,) or type_name == 'NUMERIC':
        precision = getattr(col_type, 'precision', None)
        scale = getattr(col_type, 'scale', None)
        if precision is not None and scale is not None:
            return f'NUMERIC({precision},{scale})'
        return 'NUMERIC'
    if type_class in (Float,) or type_name in ('FLOAT', 'REAL'):
        return 'DOUBLE PRECISION'
    if type_name in ('DOUBLE', 'DOUBLE_PRECISION'):
        return 'DOUBLE PRECISION'

    # Date/Time
    if type_name == 'DATE':
        return 'DATE'
    if type_name in ('DATETIME', 'TIMESTAMP'):
        timezone = getattr(col_type, 'timezone', False)
        return 'TIMESTAMPTZ' if timezone else 'TIMESTAMP'
    if type_name == 'TIME':
        return 'TIME'

    # Enum
    if type_name == 'ENUM' or isinstance(col_type, Enum):
        # Use TEXT for enums to keep it simple
        return 'TEXT'

    # Binary
    if type_name in ('LARGEBINARY', 'BYTEA'):
        return 'BYTEA'

    # Fallback
    return 'TEXT'


def _col_default_clause(col) -> str:
    """Generate DEFAULT clause for a column."""
    server_default = col.server_default
    if server_default is not None:
        # Use server_default if explicitly set
        if hasattr(server_default, 'arg'):
            return f" DEFAULT {server_default.arg}"
        return f" DEFAULT {server_default}"

    # Check Python-side default
    if col.default is not None:
        dv = col.default
        if hasattr(dv, 'arg') and not callable(dv.arg):
            val = dv.arg
            if isinstance(val, bool):
                return f" DEFAULT {'TRUE' if val else 'FALSE'}"
            if isinstance(val, str):
                escaped = val.replace("'", "''")
                return f" DEFAULT '{escaped}'"
            if isinstance(val, (int, float)):
                return f" DEFAULT {val}"
            if val is None:
                return ""
            # list/dict (e.g. JSONB default=list)
            if callable(val):
                return " DEFAULT '[]'"
        if hasattr(dv, 'arg') and dv.arg is None:
            return ""

    return ""


def _col_to_sql(col) -> str:
    """Generate full column definition for ADD COLUMN."""
    pg_type = _sqlalchemy_type_to_pg(col.type)
    default = _col_default_clause(col)

    # nullable: if col is NOT NULL and no default, we must provide a default
    # to avoid breaking existing rows. Use NULL-safe fallback.
    if not col.nullable and not default:
        # Pick safe default by type
        t = pg_type.upper()
        if 'INT' in t:
            default = " DEFAULT 0"
        elif 'NUMERIC' in t or 'FLOAT' in t or 'DOUBLE' in t:
            default = " DEFAULT 0"
        elif 'BOOL' in t:
            default = " DEFAULT FALSE"
        elif 'TIMESTAMP' in t or t == 'DATE':
            default = " DEFAULT now()"
        else:
            default = " DEFAULT ''"

    null_clause = "" if col.nullable else " NOT NULL"
    return f"{col.name} {pg_type}{default}{null_clause}"


async def _fix_cascade_constraints(conn) -> None:
    """Ensure critical FK constraints have ON DELETE CASCADE.

    Phase 23.5: applied idempotently at startup (DROP IF EXISTS + ADD).
    Safe to re-run — DROP IF EXISTS is a no-op when the constraint is already correct.
    """
    fixes = [
        (
            "purchase_receipts",
            "purchase_receipts_purchase_id_fkey",
            "purchase_id",
            "purchases",
            "id",
        ),
        # Phase 23.6: payments.purchase_id had NO ACTION → blocked bulk delete of purchases
        # CASCADE: при удалении закупки платежи уходят вместе (платёж без закупки не имеет смысла)
        (
            "payments",
            "payments_purchase_id_fkey",
            "purchase_id",
            "purchases",
            "id",
        ),
    ]
    for table, constraint, col, ref_table, ref_col in fixes:
        # asyncpg НЕ поддерживает multi-statement в одном prepared statement —
        # DROP и ADD должны идти раздельно, иначе PostgresSyntaxError.
        try:
            await conn.execute(text(
                f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}"
            ))
            await conn.execute(text(
                f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
                f"FOREIGN KEY ({col}) REFERENCES {ref_table}({ref_col}) ON DELETE CASCADE"
            ))
            print(f"  ✅  cascade FK ensured: {table}.{col} → {ref_table}.{ref_col}")
        except Exception as e:
            print(f"  ⚠️   cascade FK fix failed for {table}.{constraint}: {e}")


async def _ensure_user_addresses_table(conn) -> None:
    """Phase 25: ensure user_addresses table exists (idempotent)."""
    # asyncpg: multi-statement в одном execute = PostgresSyntaxError.
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS user_addresses ("
            "id SERIAL PRIMARY KEY,"
            "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
            "address VARCHAR(500) NOT NULL,"
            "last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            "CONSTRAINT uq_user_addr UNIQUE (user_id, address))"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_user_addresses_user_id ON user_addresses (user_id)"
        ))
        print("  ✅  user_addresses table ensured")
    except Exception as e:
        print(f"  ⚠️   user_addresses table ensure failed: {e}")


async def _ensure_contract_items_table(conn) -> None:
    """Phase 27.1: ensure contract_items table exists (idempotent).

    Pattern из _ensure_user_addresses_table. asyncpg НЕ принимает multi-statement
    в одном text() — каждый CREATE/INDEX отдельным execute (Phase 27.1 Pitfall 2).
    """
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS contract_items ("
            " id SERIAL PRIMARY KEY,"
            " purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,"
            " source_item_id INTEGER REFERENCES purchase_items(id) ON DELETE SET NULL,"
            " contract_id INTEGER REFERENCES contracts(id) ON DELETE SET NULL,"
            " product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,"
            " name TEXT NOT NULL,"
            " quantity NUMERIC(15,4),"
            " unit VARCHAR(50),"
            " unit_price NUMERIC(15,2),"
            " total NUMERIC(15,2),"
            " match_confirmed BOOLEAN NOT NULL DEFAULT TRUE,"
            " created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " updated_at TIMESTAMPTZ"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_contract_items_purchase_id "
            "ON contract_items (purchase_id)"
        ))
        # Phase 27.1.17: добавить vat_rate если нет
        await conn.execute(text(
            "ALTER TABLE contract_items ADD COLUMN IF NOT EXISTS vat_rate VARCHAR(20)"
        ))
        print("  \u2705  contract_items table ensured")
    except Exception as e:
        print(f"  \u26a0\ufe0f   contract_items table ensure failed: {e}")


async def _ensure_purchase_items_receipt_id(conn) -> None:
    """Phase 26-BB: добавить receipt_id FK в purchase_items (idempotent)."""
    try:
        await conn.execute(text("""
            ALTER TABLE purchase_items
            ADD COLUMN IF NOT EXISTS receipt_id INTEGER
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_purchase_items_receipt_id
            ON purchase_items(receipt_id)
        """))
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'fk_purchase_items_receipt_id'
                ) THEN
                    ALTER TABLE purchase_items
                    ADD CONSTRAINT fk_purchase_items_receipt_id
                    FOREIGN KEY (receipt_id) REFERENCES purchase_receipts(id) ON DELETE SET NULL;
                END IF;
            END $$;
        """))
        print("  \u2705  purchase_items.receipt_id ensured (Phase 26-BB)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   purchase_items.receipt_id ensure failed: {e}")


async def _backfill_contract_items_from_purchase_items(conn) -> int:
    """Phase 27.1 D-06: idempotent backfill 1\u21941 \u0434\u043b\u044f legacy \u0437\u0430\u043a\u0443\u043f\u043e\u043a \u0432 contracted+.

    Returns: \u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e backfilled contract_items (\u0434\u043b\u044f \u043b\u043e\u0433\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f).
    """
    # \u0428\u0430\u0433 1: \u0441\u043e\u0437\u0434\u0430\u0442\u044c contract_items \u0434\u043b\u044f \u0437\u0430\u043a\u0443\u043f\u043e\u043a \u0432 contracted/ordered/delivered/paid \u0431\u0435\u0437 contract_items
    result = await conn.execute(text(
        "INSERT INTO contract_items"
        " (purchase_id, source_item_id, product_id, name, quantity, unit, unit_price, total, match_confirmed)"
        " SELECT pi.purchase_id, pi.id, pi.product_id, pi.item_name,"
        "        pi.quantity, pi.unit, pi.unit_price, pi.total_price, TRUE"
        " FROM purchase_items pi"
        " JOIN purchases p ON p.id = pi.purchase_id"
        " WHERE p.status IN ('contracted', 'ordered', 'delivered', 'paid')"
        "   AND NOT EXISTS ("
        "       SELECT 1 FROM contract_items ci WHERE ci.purchase_id = pi.purchase_id"
        "   )"
    ))
    # \u0428\u0430\u0433 2: \u043f\u0435\u0440\u0435\u0441\u0447\u0438\u0442\u0430\u0442\u044c contract_price \u0434\u043b\u044f non-framework-head (D-07)
    await conn.execute(text(
        "UPDATE purchases p"
        " SET contract_price = ("
        "     SELECT COALESCE(SUM(ci.total), p.contract_price)"
        "     FROM contract_items ci WHERE ci.purchase_id = p.id"
        " )"
        " WHERE p.status IN ('contracted','ordered','delivered','paid')"
        "   AND (p.purchase_contract_type NOT IN ('framework_cumulative','framework_limited')"
        "        OR p.parent_purchase_id IS NOT NULL)"
    ))
    return result.rowcount or 0


async def _ensure_framework_seq_unique_index(conn) -> None:
    """Phase 27.1.4: partial unique index on (contract_id, framework_seq) WHERE both NOT NULL.

    ПЕРЕД созданием индекса — bump дубликаты (перенумеровать), иначе CREATE INDEX упадёт.
    Idempotent: IF NOT EXISTS гарантирует повторный запуск без ошибки.
    """
    try:
        # Шаг 1: найти группы дублей и перенумеровать (оставить min(id), остальным → MAX+offset)
        dup_result = await conn.execute(text("""
            SELECT contract_id, framework_seq, array_agg(id ORDER BY id) AS ids
            FROM purchases
            WHERE contract_id IS NOT NULL AND framework_seq IS NOT NULL
            GROUP BY contract_id, framework_seq
            HAVING COUNT(*) > 1
        """))
        dup_rows = dup_result.fetchall()
        if dup_rows:
            print(f"  ⚠️   framework_seq: found {len(dup_rows)} duplicate group(s), bumping...")
            for row in dup_rows:
                contract_id, framework_seq, ids = row
                # Keep min(id) with original seq, bump others
                # Find max framework_seq for this contract to safely offset
                max_seq_result = await conn.execute(text(
                    "SELECT COALESCE(MAX(framework_seq), 0) FROM purchases WHERE contract_id = :cid"
                ), {"cid": contract_id})
                max_seq = max_seq_result.scalar() or 0
                # ids is sorted asc — first is the keeper, rest get bumped
                for offset, dup_id in enumerate(ids[1:], start=1):
                    new_seq = max_seq + offset + 1000  # safe offset above current max
                    await conn.execute(text(
                        "UPDATE purchases SET framework_seq = :seq WHERE id = :id"
                    ), {"seq": new_seq, "id": dup_id})
            print(f"  ✅  framework_seq duplicates resolved")

        # Шаг 2: создать partial unique index (idempotent)
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_framework_seq
            ON purchases (contract_id, framework_seq)
            WHERE contract_id IS NOT NULL AND framework_seq IS NOT NULL
        """))
        print("  ✅  uq_purchase_framework_seq partial unique index ensured (Phase 27.1.4)")
    except Exception as e:
        print(f"  ⚠️   uq_purchase_framework_seq ensure failed: {e}")


async def _ensure_plan_graph_versions_table(conn) -> None:
    """Phase 12-03: ensure plan_graph_versions table exists (idempotent)."""
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS plan_graph_versions ("
            " id SERIAL PRIMARY KEY,"
            " subsidy_id INTEGER NOT NULL REFERENCES subsidies(id) ON DELETE CASCADE,"
            " version_number INTEGER NOT NULL,"
            " created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
            " created_by_name VARCHAR(200),"
            " snapshot JSONB NOT NULL,"
            " note TEXT"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_plan_graph_versions_subsidy_id "
            "ON plan_graph_versions (subsidy_id)"
        ))
        print("  \u2705  plan_graph_versions table ensured")
    except Exception as e:
        print(f"  \u26a0\ufe0f   plan_graph_versions table ensure failed: {e}")


async def main(apply: bool = False) -> int:
    async with engine.begin() as conn:
        # Phase 23.5: ensure critical FK cascades (idempotent)
        if apply:
            print("Fixing cascade FK constraints...")
            await _fix_cascade_constraints(conn)

        # Phase 25: ensure user_addresses table exists
        if apply:
            await _ensure_user_addresses_table(conn)

        # Phase 27.1: ensure contract_items table exists
        if apply:
            await _ensure_contract_items_table(conn)

        # Phase 27.1.4: partial unique index on (contract_id, framework_seq) WHERE both NOT NULL
        if apply:
            await _ensure_framework_seq_unique_index(conn)

        # Phase 12-03: ensure plan_graph_versions table exists
        if apply:
            await _ensure_plan_graph_versions_table(conn)

        # Fetch all existing columns from the DB
        result = await conn.execute(text("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
        """))
        db_cols: dict[str, set] = {}
        for table_name, col_name in result:
            db_cols.setdefault(table_name, set()).add(col_name)

        # Compare with SQLAlchemy metadata
        alters: list[tuple[str, str]] = []  # (table, full ALTER statement)
        for table_name, table in sorted(Base.metadata.tables.items()):
            actual = db_cols.get(table_name, set())
            for col in table.columns:
                if col.name not in actual:
                    col_def = _col_to_sql(col)
                    stmt = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col_def};"
                    alters.append((table_name, stmt))

        if not alters:
            print("✅  Schema is up to date — no missing columns.")
            return 0

        print(f"⚠️   Found {len(alters)} missing column(s):\n")
        for _, stmt in alters:
            print(f"    {stmt}")

        if not apply:
            print("\nRun with --apply to fix automatically.")
            return 1

        print("\nApplying migrations...")
        errors = []
        for _, stmt in alters:
            try:
                await conn.execute(text(stmt))
                print(f"  ✅  {stmt}")
            except Exception as e:
                print(f"  ❌  FAILED: {stmt}")
                print(f"       {e}")
                errors.append((stmt, str(e)))

        if errors:
            print(f"\n❌  {len(errors)} statement(s) failed — check above.")
            return 1

        print(f"\n✅  All {len(alters)} column(s) added successfully.")
        return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    exit_code = asyncio.run(main(apply=apply))
    sys.exit(exit_code)
