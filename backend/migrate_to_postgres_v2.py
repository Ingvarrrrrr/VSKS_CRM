#!/usr/bin/env python3
"""
Миграция VSKS CRM с SQLite на PostgreSQL с правильным порядком таблиц
"""

import asyncio
import sys
from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SQLITE_URL = "sqlite:///./vsks.db"
POSTGRES_URL = "postgresql+asyncpg://clawd@localhost/vsks_crm"

# Порядок таблиц согласно зависимостям внешних ключей
TABLE_ORDER = [
    'subsidies',        # независимая
    'users',            # независимая
    'contractors',      # независимая
    'feo_categories',   # зависит от subsidies
    'products',         # зависит от feo_categories
    'contracts',        # зависит от contractors
    'purchases',        # зависит от feo_categories, contractors, contracts
    'payments',         # зависит от contracts, purchases
]

async def create_tables():
    """Создать таблицы в PostgreSQL через SQLAlchemy модели"""
    # Импортируем здесь, чтобы не мешать зависимости
    sys.path.insert(0, '.')
    from app.database import Base
    from app.models import subsidy, feo_category, product, contractor, contract, purchase, payment, user
    
    engine = create_async_engine(POSTGRES_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Таблицы созданы в PostgreSQL")
    await engine.dispose()

async def copy_data_in_order():
    """Копировать данные в правильном порядке"""
    sqlite_engine = create_engine(SQLITE_URL)
    sqlite_metadata = MetaData()
    sqlite_metadata.reflect(bind=sqlite_engine)
    
    postgres_engine = create_async_engine(POSTGRES_URL, echo=False)
    
    for table_name in TABLE_ORDER:
        if table_name not in sqlite_metadata.tables:
            logger.warning(f"Таблица {table_name} не найдена в SQLite, пропускаем")
            continue
        
        table = sqlite_metadata.tables[table_name]
        logger.info(f"Копируем таблицу: {table_name}")
        
        with sqlite_engine.connect() as conn:
            result = conn.execute(select(table)).fetchall()
            logger.info(f"  Записей: {len(result)}")
            
            if not result:
                continue
            
            async with AsyncSession(postgres_engine) as session:
                async with session.begin():
                    for row in result:
                        row_dict = {column.name: value for column, value in zip(table.columns, row)}
                        insert_stmt = table.insert().values(**row_dict)
                        await session.execute(insert_stmt)
                
                await session.commit()
                logger.info(f"  Скопировано: {len(result)}")
    
    sqlite_engine.dispose()
    await postgres_engine.dispose()
    logger.info("Все данные скопированы")

async def main():
    logger.info("Начинаем миграцию SQLite → PostgreSQL")
    
    try:
        # 1. Создать таблицы
        await create_tables()
        
        # 2. Скопировать данные
        await copy_data_in_order()
        
        logger.info("✅ Миграция успешно завершена!")
        logger.info("База данных PostgreSQL готова к использованию.")
        
    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())