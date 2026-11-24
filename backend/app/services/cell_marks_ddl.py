import logging
from sqlalchemy import text
from app.database import engine

logger = logging.getLogger(__name__)

DDL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS cell_marks (
        id SERIAL PRIMARY KEY,
        group_id VARCHAR(36) NOT NULL,
        entity_type VARCHAR(40) NOT NULL,
        entity_id INTEGER NOT NULL,
        field_name VARCHAR(80) NOT NULL DEFAULT '*',
        org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
        subsidy_id INTEGER REFERENCES subsidies(id) ON DELETE CASCADE,
        color VARCHAR(24),
        comment TEXT,
        visibility VARCHAR(16) NOT NULL DEFAULT 'shared',
        is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
        resolved_at TIMESTAMPTZ,
        resolved_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        resolved_by_name VARCHAR(255),
        created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_by_name VARCHAR(255),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_cell_marks_group_id ON cell_marks (group_id)",
    "CREATE INDEX IF NOT EXISTS ix_cell_marks_entity_type ON cell_marks (entity_type)",
    "CREATE INDEX IF NOT EXISTS ix_cell_marks_entity_id ON cell_marks (entity_id)",
    "CREATE INDEX IF NOT EXISTS ix_cell_marks_lookup ON cell_marks (entity_type, entity_id, field_name)",
    "CREATE INDEX IF NOT EXISTS ix_cell_marks_org_id ON cell_marks (org_id)",
    "CREATE INDEX IF NOT EXISTS ix_cell_marks_subsidy_id ON cell_marks (subsidy_id)",
    "CREATE INDEX IF NOT EXISTS ix_cell_marks_is_resolved ON cell_marks (is_resolved)",
    "CREATE INDEX IF NOT EXISTS ix_cell_marks_created_by_id ON cell_marks (created_by_id)",
]


async def ensure_cell_marks_schema() -> None:
    """Idempotent DDL helper for cell_marks table executing statements individually."""
    try:
        async with engine.begin() as conn:
            for stmt in DDL_STATEMENTS:
                await conn.execute(text(stmt))
    except Exception as e:
        logger.warning(f"cell_marks schema setup skipped (non-fatal): {e}")
