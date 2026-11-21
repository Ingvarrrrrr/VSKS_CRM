import logging
from sqlalchemy import text
from app.database import engine

logger = logging.getLogger(__name__)


async def ensure_delivery_items_schema() -> None:
    """Phase 27: Idempotent DDL helper for delivery_items table."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS delivery_items (
                    id SERIAL PRIMARY KEY,
                    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
                    contract_item_id INTEGER REFERENCES contract_items(id) ON DELETE SET NULL,
                    purchase_item_id INTEGER REFERENCES purchase_items(id) ON DELETE SET NULL,
                    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                    name TEXT NOT NULL,
                    unit VARCHAR(50),
                    qty NUMERIC(14, 4) NOT NULL DEFAULT 0,
                    unit_price NUMERIC(14, 2) NOT NULL DEFAULT 0,
                    total NUMERIC(14, 2) NOT NULL DEFAULT 0,
                    delivery_date DATE,
                    doc_number VARCHAR(255),
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS ix_delivery_items_purchase_id ON delivery_items (purchase_id);
                CREATE INDEX IF NOT EXISTS ix_delivery_items_contract_item_id ON delivery_items (contract_item_id);
                CREATE INDEX IF NOT EXISTS ix_delivery_items_purchase_item_id ON delivery_items (purchase_item_id);
                CREATE INDEX IF NOT EXISTS ix_delivery_items_product_id ON delivery_items (product_id);
            """))
    except Exception as e:
        logger.warning(f"Phase 27 delivery_items schema setup skipped (non-fatal): {e}")
