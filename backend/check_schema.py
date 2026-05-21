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


async def _ensure_external_drivers_table(conn) -> None:
    """Phase 29-02: ensure external_drivers table exists (idempotent).

    D-15: наёмные водители без аккаунта в системе.
    Порядок: external_drivers ДО trips (FK driver_external_id).
    """
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS external_drivers ("
            " id SERIAL PRIMARY KEY,"
            " full_name VARCHAR(255) NOT NULL,"
            " phone VARCHAR(30),"
            " license_series VARCHAR(10),"
            " license_number VARCHAR(20),"
            " license_categories VARCHAR(50),"
            " license_issued_at DATE,"
            " license_expires_at DATE,"
            " medical_cert_expires_at DATE,"
            " org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,"
            " notes TEXT,"
            " created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_external_drivers_full_name"
            " ON external_drivers (full_name)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_external_drivers_org_id"
            " ON external_drivers (org_id)"
        ))
        print("  \u2705  external_drivers table ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   external_drivers table ensure failed: {e}")


async def _ensure_vehicles_table(conn) -> None:
    """Phase 29-02: ensure vehicles table exists (idempotent).

    D-06, D-08, D-20: основная карточка ТС.
    VARCHAR вместо PG ENUM — проще миграции.
    """
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS vehicles ("
            " id SERIAL PRIMARY KEY,"
            " owner_org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,"
            " assigned_org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,"
            " assigned_text VARCHAR(100),"
            " brand VARCHAR(100),"
            " model VARCHAR(100),"
            " color VARCHAR(50),"
            " vin VARCHAR(17),"
            " plate VARCHAR(20) NOT NULL,"
            " registered_at DATE,"
            " insurance_until DATE,"
            " type VARCHAR(30),"
            " state VARCHAR(20) DEFAULT 'working',"
            " fuel_type VARCHAR(20),"
            " fuel_norm_summer DOUBLE PRECISION,"
            " fuel_norm_winter DOUBLE PRECISION,"
            " has_tracker BOOLEAN,"
            " akb_ok BOOLEAN,"
            " has_radio BOOLEAN,"
            " mirrors_ok BOOLEAN,"
            " has_keys BOOLEAN,"
            " has_first_aid_kit BOOLEAN,"
            " has_spare_wheel BOOLEAN,"
            " has_extinguisher BOOLEAN,"
            " next_to_km INTEGER,"
            " current_odometer_km INTEGER,"
            " props JSONB NOT NULL DEFAULT '{}'::jsonb,"
            " created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " CONSTRAINT uq_vehicles_plate UNIQUE (plate)"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicles_owner_org_id ON vehicles (owner_org_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicles_assigned_org_id ON vehicles (assigned_org_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicles_plate ON vehicles (plate)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicles_state ON vehicles (state)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicles_type ON vehicles (type)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicles_vin ON vehicles (vin)"
        ))
        print("  \u2705  vehicles table ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   vehicles table ensure failed: {e}")


async def _ensure_vehicle_attachments_table(conn) -> None:
    """Phase 29-02: ensure vehicle_attachments table exists (idempotent).

    D-07, D-11: документы и фото ТС (bytea + SHA-256 dedup).
    """
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS vehicle_attachments ("
            " id SERIAL PRIMARY KEY,"
            " vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,"
            " kind VARCHAR(20) NOT NULL DEFAULT 'other',"
            " name VARCHAR(500) NOT NULL,"
            " file_data BYTEA NOT NULL,"
            " mime VARCHAR(100),"
            " size INTEGER,"
            " sha256 VARCHAR(64),"
            " uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " uploaded_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
            " policy_number VARCHAR(50),"
            " issued_at DATE,"
            " expires_at DATE"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_attachments_vehicle_id"
            " ON vehicle_attachments (vehicle_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_attachments_sha256"
            " ON vehicle_attachments (sha256)"
        ))
        print("  \u2705  vehicle_attachments table ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   vehicle_attachments table ensure failed: {e}")


async def _ensure_vehicle_repairs_table(conn) -> None:
    """Phase 29-02: ensure vehicle_repairs table exists (idempotent).

    D-12, D-18: ремонты ТС + nullable purchase_id FK.
    """
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS vehicle_repairs ("
            " id SERIAL PRIMARY KEY,"
            " vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,"
            " date DATE NOT NULL,"
            " description TEXT,"
            " cost_amount NUMERIC(12,2),"
            " performed_by_name VARCHAR(255),"
            " mileage_at_repair INTEGER,"
            " status VARCHAR(20) NOT NULL DEFAULT 'planned',"
            " purchase_id INTEGER REFERENCES purchases(id) ON DELETE SET NULL,"
            " created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_repairs_vehicle_id"
            " ON vehicle_repairs (vehicle_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_repairs_status"
            " ON vehicle_repairs (status)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_repairs_purchase_id"
            " ON vehicle_repairs (purchase_id)"
        ))
        print("  \u2705  vehicle_repairs table ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   vehicle_repairs table ensure failed: {e}")


async def _ensure_repair_attachments_table(conn) -> None:
    """Phase 29-02: ensure repair_attachments table exists (idempotent).

    D-07, D-12: документы по конкретному ремонту ТС.
    """
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS repair_attachments ("
            " id SERIAL PRIMARY KEY,"
            " repair_id INTEGER NOT NULL REFERENCES vehicle_repairs(id) ON DELETE CASCADE,"
            " kind VARCHAR(20) NOT NULL DEFAULT 'other',"
            " name VARCHAR(500) NOT NULL,"
            " file_data BYTEA NOT NULL,"
            " mime VARCHAR(100),"
            " size INTEGER,"
            " sha256 VARCHAR(64),"
            " uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " uploaded_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_repair_attachments_repair_id"
            " ON repair_attachments (repair_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_repair_attachments_sha256"
            " ON repair_attachments (sha256)"
        ))
        print("  \u2705  repair_attachments table ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   repair_attachments table ensure failed: {e}")


async def _ensure_vehicle_field_history_table(conn) -> None:
    """Phase 29-02: ensure vehicle_field_history table exists (idempotent).

    D-10: аудит-лог изменений полей карточки ТС.
    """
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS vehicle_field_history ("
            " id SERIAL PRIMARY KEY,"
            " vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,"
            " field_key VARCHAR(64) NOT NULL,"
            " old_value TEXT,"
            " new_value TEXT,"
            " changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " changed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
            " comment TEXT"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_field_history_vehicle_id"
            " ON vehicle_field_history (vehicle_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_field_history_field_key"
            " ON vehicle_field_history (field_key)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_field_history_changed_at"
            " ON vehicle_field_history (changed_at)"
        ))
        print("  \u2705  vehicle_field_history table ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   vehicle_field_history table ensure failed: {e}")


async def _ensure_vehicle_odometer_table(conn) -> None:
    """Phase 29-02: ensure vehicle_odometer table exists (idempotent).

    D-13: абсолютные значения пробега, UNIQUE(vehicle_id, date).
    """
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS vehicle_odometer ("
            " id SERIAL PRIMARY KEY,"
            " vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,"
            " date DATE NOT NULL,"
            " odometer_km INTEGER NOT NULL,"
            " entered_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
            " note TEXT,"
            " source VARCHAR(20) NOT NULL DEFAULT 'manual',"
            " created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " CONSTRAINT uq_vehicle_odometer_vehicle_date UNIQUE (vehicle_id, date)"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_odometer_vehicle_id_date_desc"
            " ON vehicle_odometer (vehicle_id, date DESC)"
        ))
        print("  \u2705  vehicle_odometer table ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   vehicle_odometer table ensure failed: {e}")


async def _ensure_fuel_logs_table(conn) -> None:
    """Phase 29-02: ensure fuel_logs table exists (idempotent).

    D-03, D-20: журнал заправок ТС.
    """
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS fuel_logs ("
            " id SERIAL PRIMARY KEY,"
            " vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,"
            " date DATE NOT NULL,"
            " liters NUMERIC(8,2),"
            " price_per_liter NUMERIC(8,2),"
            " total_amount NUMERIC(12,2),"
            " fuel_type VARCHAR(20),"
            " receipt_attachment_id INTEGER REFERENCES vehicle_attachments(id) ON DELETE SET NULL,"
            " note TEXT,"
            " source VARCHAR(20) NOT NULL DEFAULT 'manual',"
            " created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fuel_logs_vehicle_id ON fuel_logs (vehicle_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fuel_logs_vehicle_id_date_desc"
            " ON fuel_logs (vehicle_id, date DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fuel_logs_date ON fuel_logs (date)"
        ))
        print("  \u2705  fuel_logs table ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   fuel_logs table ensure failed: {e}")


async def _ensure_trips_table(conn) -> None:
    """Phase 29-02: ensure trips table exists (idempotent).

    D-14, D-15, D-19: путевые листы ТС.
    CHECK constraint: driver_user_id XOR driver_external_id (D-15).
    """
    try:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS trips ("
            " id SERIAL PRIMARY KEY,"
            " vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,"
            " date DATE NOT NULL,"
            " driver_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
            " driver_external_id INTEGER REFERENCES external_drivers(id) ON DELETE SET NULL,"
            " route_from VARCHAR(255),"
            " route_to VARCHAR(255),"
            " purpose TEXT,"
            " odometer_start INTEGER,"
            " odometer_finish INTEGER,"
            " fuel_remaining_start NUMERIC(6,2),"
            " fuel_remaining_finish NUMERIC(6,2),"
            " fuel_issued_l NUMERIC(6,2),"
            " cargo_name VARCHAR(255),"
            " cargo_weight_t NUMERIC(8,2),"
            " docx_path VARCHAR(500),"
            " status VARCHAR(20) NOT NULL DEFAULT 'draft',"
            " created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
            " CONSTRAINT ck_trip_driver_xor"
            "   CHECK (driver_user_id IS NOT NULL OR driver_external_id IS NOT NULL)"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_trips_vehicle_id ON trips (vehicle_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_trips_date ON trips (date DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_trips_status ON trips (status)"
        ))
        print("  \u2705  trips table ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   trips table ensure failed: {e}")


async def _ensure_purchases_vehicle_id(conn) -> None:
    """Phase 29-02: ALTER purchases — add vehicle_id FK (D-18, idempotent)."""
    try:
        await conn.execute(text(
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS"
            " vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_purchases_vehicle_id"
            " ON purchases (vehicle_id) WHERE vehicle_id IS NOT NULL"
        ))
        print("  \u2705  purchases.vehicle_id column ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   purchases.vehicle_id ensure failed: {e}")


async def _ensure_users_driver_columns(conn) -> None:
    """Phase 29-02: ALTER users — add 7 driver columns (D-04, idempotent).

    asyncpg multi-statement bug: каждый ALTER отдельным execute.
    """
    try:
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS"
            " can_drive BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS license_series VARCHAR(10)"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS license_number VARCHAR(20)"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS license_categories VARCHAR(50)"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS license_issued_at DATE"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS license_expires_at DATE"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS medical_cert_expires_at DATE"
        ))
        print("  \u2705  users driver columns ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   users driver columns ensure failed: {e}")


async def _ensure_vehicles_new_columns(conn) -> None:
    """Phase 29-3a2: ALTER vehicles — 7 новых колонок из реестра Голичкова (idempotent).

    asyncpg multi-statement bug: каждый ALTER отдельным execute.
    """
    try:
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS year_of_manufacture INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS last_to_mileage_km INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS last_to_date DATE"
        ))
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS pts_number VARCHAR(50)"
        ))
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS sts_number VARCHAR(50)"
        ))
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS tech_inspection_until DATE"
        ))
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS purchase_info VARCHAR(200)"
        ))
        print("  \u2705  vehicles new columns ensured (Phase 29-3a2)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   vehicles new columns ensure failed: {e}")


async def _ensure_vehicles_assignment_columns(conn) -> None:
    """Phase 29.3: ALTER vehicles — 5 новых колонок (assignment_basis, doc, engine) — idempotent."""
    try:
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS assignment_basis VARCHAR(200)"
        ))
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS assignment_doc_number VARCHAR(100)"
        ))
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS assignment_doc_date DATE"
        ))
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS engine_power_hp INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS engine_volume_l DOUBLE PRECISION"
        ))
        print("  \u2705  vehicles assignment+engine columns ensured (Phase 29.3)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   vehicles assignment columns ensure failed: {e}")


async def _ensure_vehicle_transfer_history_table(conn) -> None:
    """Phase 29.3: CREATE vehicle_transfer_history table (idempotent)."""
    try:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vehicle_transfer_history (
                id SERIAL PRIMARY KEY,
                vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                from_owner_org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
                to_owner_org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
                from_assigned_org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
                to_assigned_org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
                from_assigned_text VARCHAR(100),
                to_assigned_text VARCHAR(100),
                basis VARCHAR(200),
                doc_number VARCHAR(100),
                doc_date DATE,
                comment TEXT,
                changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                changed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_transfer_history_vehicle_id"
            " ON vehicle_transfer_history (vehicle_id)"
        ))
        print("  \u2705  vehicle_transfer_history table ensured (Phase 29.3)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   vehicle_transfer_history table ensure failed: {e}")


async def _ensure_vehicle_fines_table(conn) -> None:
    """Phase 29.3-fines: CREATE vehicle_fines table with indexes (idempotent)."""
    try:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vehicle_fines (
                id SERIAL PRIMARY KEY,
                vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                issued_at TIMESTAMPTZ NOT NULL,
                amount NUMERIC(12, 2) NOT NULL,
                doc_number VARCHAR(100),
                violation_type VARCHAR(200),
                location VARCHAR(500),
                status VARCHAR(20) NOT NULL DEFAULT 'unpaid',
                paid_at TIMESTAMPTZ,
                comment TEXT,
                driver_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                driver_external_id INTEGER REFERENCES external_drivers(id) ON DELETE SET NULL,
                matched_trip_id INTEGER REFERENCES trips(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_fines_vehicle_id ON vehicle_fines (vehicle_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_fines_issued_at ON vehicle_fines (issued_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vehicle_fines_status ON vehicle_fines (status)"
        ))
        print("  \u2705  vehicle_fines table ensured (Phase 29.3-fines)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   vehicle_fines table ensure failed: {e}")


async def _ensure_tasks_system_tag(conn) -> None:
    """Phase 29-02: ALTER tasks — add system_tag column + partial index (D-17, idempotent)."""
    try:
        await conn.execute(text(
            "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS system_tag VARCHAR(200)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_tasks_system_tag"
            " ON tasks (system_tag) WHERE system_tag IS NOT NULL"
        ))
        print("  \u2705  tasks.system_tag column ensured (Phase 29-02)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   tasks.system_tag ensure failed: {e}")


async def _ensure_organizations_color(conn) -> None:
    """Phase 29.3: ALTER organizations — add color column (idempotent)."""
    try:
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS color VARCHAR(20)"))
        print("  \u2705  organizations.color ensured (Phase 29.3)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   organizations.color ensure failed: {e}")


async def _ensure_trips_waybill_columns(conn) -> None:
    """Phase 30: ALTER trips — add waybill columns (number/dates/dispatcher/осмотры/driver_signature) — idempotent."""
    try:
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS number VARCHAR(20) UNIQUE"))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS date_start TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS date_end TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS planned_mileage_km INTEGER"))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS actual_mileage_km INTEGER"))
        await conn.execute(text(
            "ALTER TABLE trips ADD COLUMN IF NOT EXISTS"
            " dispatcher_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
        ))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS cargo_description TEXT"))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS passengers_count INTEGER"))
        # Pre-trip
        await conn.execute(text(
            "ALTER TABLE trips ADD COLUMN IF NOT EXISTS"
            " pre_trip_mechanic_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
        ))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS pre_trip_mechanic_inspected_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS pre_trip_mechanic_result TEXT"))
        await conn.execute(text(
            "ALTER TABLE trips ADD COLUMN IF NOT EXISTS"
            " pre_trip_doctor_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
        ))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS pre_trip_doctor_inspected_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS pre_trip_doctor_result TEXT"))
        # Post-trip
        await conn.execute(text(
            "ALTER TABLE trips ADD COLUMN IF NOT EXISTS"
            " post_trip_mechanic_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
        ))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS post_trip_mechanic_inspected_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS post_trip_mechanic_result TEXT"))
        await conn.execute(text(
            "ALTER TABLE trips ADD COLUMN IF NOT EXISTS"
            " post_trip_doctor_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
        ))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS post_trip_doctor_inspected_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS post_trip_doctor_result TEXT"))
        # Driver signature
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS driver_signature TEXT"))
        await conn.execute(text("ALTER TABLE trips ADD COLUMN IF NOT EXISTS driver_signed_at TIMESTAMPTZ"))
        print("  \u2705  trips waybill columns ensured (Phase 30)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   trips waybill columns ensure failed: {e}")


async def _ensure_fleet_documents_table(conn) -> None:
    """Phase 30: CREATE fleet_documents table with migration from vehicle fields (idempotent)."""
    try:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fleet_documents (
                id SERIAL PRIMARY KEY,
                vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                type VARCHAR(30) NOT NULL,
                number VARCHAR(100),
                issued_at DATE,
                expires_at DATE,
                counterparty VARCHAR(200),
                amount_rub NUMERIC(12, 2),
                file_url VARCHAR(500),
                file_data BYTEA,
                file_name VARCHAR(200),
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fleet_documents_vehicle_id ON fleet_documents (vehicle_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fleet_documents_type ON fleet_documents (type)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fleet_documents_expires_at ON fleet_documents (expires_at)"
        ))
        # Идемпотентная миграция данных из Vehicle полей
        await conn.execute(text("""
            INSERT INTO fleet_documents (vehicle_id, type, expires_at, created_at)
            SELECT v.id, 'osago', v.insurance_until, NOW()
            FROM vehicles v
            WHERE v.insurance_until IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM fleet_documents d WHERE d.vehicle_id = v.id AND d.type = 'osago')
        """))
        await conn.execute(text("""
            INSERT INTO fleet_documents (vehicle_id, type, number, created_at)
            SELECT v.id, 'pts', v.pts_number, NOW()
            FROM vehicles v
            WHERE v.pts_number IS NOT NULL AND v.pts_number != ''
              AND NOT EXISTS (SELECT 1 FROM fleet_documents d WHERE d.vehicle_id = v.id AND d.type = 'pts')
        """))
        await conn.execute(text("""
            INSERT INTO fleet_documents (vehicle_id, type, number, created_at)
            SELECT v.id, 'sts', v.sts_number, NOW()
            FROM vehicles v
            WHERE v.sts_number IS NOT NULL AND v.sts_number != ''
              AND NOT EXISTS (SELECT 1 FROM fleet_documents d WHERE d.vehicle_id = v.id AND d.type = 'sts')
        """))
        await conn.execute(text("""
            INSERT INTO fleet_documents (vehicle_id, type, expires_at, created_at)
            SELECT v.id, 'to', v.tech_inspection_until, NOW()
            FROM vehicles v
            WHERE v.tech_inspection_until IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM fleet_documents d WHERE d.vehicle_id = v.id AND d.type = 'to')
        """))
        print("  \u2705  fleet_documents table + migration ensured (Phase 30)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   fleet_documents table ensure failed: {e}")


async def _ensure_users_driver_extended(conn) -> None:
    """Phase 30: ALTER users — add 4 extended driver columns (idempotent).

    asyncpg multi-statement bug: каждый ALTER отдельным execute.
    """
    try:
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS medical_cert_number VARCHAR(50)"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS driver_tab_number VARCHAR(20)"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS experience_years INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS fleet_role VARCHAR(20)"
        ))
        print("  \u2705  users driver extended columns ensured (Phase 30)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   users driver extended columns ensure failed: {e}")


async def _ensure_organizations_geo_fields(conn) -> None:
    """Phase 30: ALTER organizations — add lat/lon/region/head_user_id (idempotent)."""
    try:
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS lat NUMERIC(9,6)"))
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS lon NUMERIC(9,6)"))
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS region VARCHAR(100)"))
        await conn.execute(text(
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS"
            " head_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
        ))
        print("  \u2705  organizations geo fields ensured (Phase 30)")
    except Exception as e:
        print(f"  \u26a0\ufe0f   organizations geo fields ensure failed: {e}")


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

        # Phase 29-02: vehicle fleet tables + ALTER purchases/users/tasks
        if apply:
            # Order matters: external_drivers before trips (FK), vehicles before everything else
            for _fn in [
                _ensure_external_drivers_table,
                _ensure_vehicles_table,
                _ensure_vehicle_attachments_table,
                _ensure_vehicle_repairs_table,
                _ensure_repair_attachments_table,
                _ensure_vehicle_field_history_table,
                _ensure_vehicle_odometer_table,
                _ensure_fuel_logs_table,
                _ensure_trips_table,
                _ensure_purchases_vehicle_id,
                _ensure_users_driver_columns,
                _ensure_tasks_system_tag,
                _ensure_vehicles_new_columns,  # Phase 29-3a2: 7 новых колонок реестра
            ]:
                try:
                    await _fn(conn)
                except Exception as e:
                    print(f"  \u26a0\ufe0f   Phase 29-02 {_fn.__name__} failed: {e}")

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
