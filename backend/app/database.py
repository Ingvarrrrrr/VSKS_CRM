import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=10,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with async_session() as session:
        yield session


async def ensure_phase22_columns() -> None:
    """Idempotent ALTER TABLE — добавляет basis_doc_number / basis_doc_date в subsidies.

    Вызывается из lifespan один раз при старте. Каждый ALTER в отдельной BEGIN/COMMIT
    транзакции — Postgres падает на «column already exists» если не использовать IF NOT EXISTS,
    но IF NOT EXISTS делает это безопасным и идемпотентным.
    """
    from sqlalchemy import text
    alters = [
        "ALTER TABLE subsidies ADD COLUMN IF NOT EXISTS basis_doc_number VARCHAR(100)",
        "ALTER TABLE subsidies ADD COLUMN IF NOT EXISTS basis_doc_date DATE",
    ]
    try:
        async with engine.begin() as conn:
            for sql in alters:
                await conn.execute(text(sql))
        logger.info("ensure_phase22_columns: subsidies.basis_doc_number / basis_doc_date OK")
    except Exception as exc:
        logger.warning("ensure_phase22_columns: non-fatal error — %s", exc)
