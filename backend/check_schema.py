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


async def main(apply: bool = False) -> int:
    async with engine.begin() as conn:
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
