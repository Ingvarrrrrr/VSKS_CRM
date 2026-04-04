#!/usr/bin/env python3
"""
Миграция VSKS CRM с SQLite на PostgreSQL
1. Создаёт таблицы в PostgreSQL
2. Копирует данные
3. Обновляет конфигурацию
"""

import asyncio
import sys
from sqlalchemy import create_engine, MetaData, Table, select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# URL баз данных
SQLITE_URL = "sqlite:///./vsks.db"
POSTGRES_URL = "postgresql+asyncpg://clawd@localhost/vsks_crm"

async def create_postgres_tables():
    """Создать все таблицы в PostgreSQL на основе моделей SQLAlchemy"""
    from app.database import Base
    from app.models import subsidy, feo_category, product, contractor, contract, purchase, payment, user
    
    # Создаём асинхронный движок PostgreSQL
    engine = create_async_engine(POSTGRES_URL, echo=True)
    
    async with engine.begin() as conn:
        # Создаём все таблицы
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Таблицы созданы в PostgreSQL")
    
    await engine.dispose()

async def copy_data():
    """Копировать данные из SQLite в PostgreSQL"""
    # Синхронный движок для SQLite
    sqlite_engine = create_engine(SQLITE_URL)
    sqlite_metadata = MetaData()
    sqlite_metadata.reflect(bind=sqlite_engine)
    
    # Асинхронный движок для PostgreSQL
    postgres_engine = create_async_engine(POSTGRES_URL, echo=False)
    
    # Исключаем таблицу alembic_version
    tables = [t for t in sqlite_metadata.tables.keys() if t != 'alembic_version']
    
    for table_name in tables:
        logger.info(f"Копируем таблицу: {table_name}")
        table = sqlite_metadata.tables[table_name]
        
        # Читаем данные из SQLite
        with sqlite_engine.connect() as conn:
            result = conn.execute(select(table)).fetchall()
            logger.info(f"  Записей: {len(result)}")
            
            if not result:
                continue
            
            # Вставляем в PostgreSQL
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
    logger.info("Данные скопированы")

async def update_config():
    """Обновить DATABASE_URL в конфиге на PostgreSQL"""
    config_path = "app/config.py"
    with open(config_path, 'r') as f:
        content = f.read()
    
    # Заменяем SQLite URL на PostgreSQL
    new_content = content.replace(
        'DATABASE_URL: str = "sqlite+aiosqlite:///./vsks.db"',
        'DATABASE_URL: str = "postgresql+asyncpg://clawd@localhost/vsks_crm"'
    )
    
    with open(config_path, 'w') as f:
        f.write(new_content)
    
    logger.info("Конфиг обновлён на PostgreSQL")

async def main():
    logger.info("Начинаем миграцию SQLite → PostgreSQL")
    
    try:
        # 1. Создать таблицы
        await create_postgres_tables()
        
        # 2. Скопировать данные
        await copy_data()
        
        # 3. Обновить конфиг
        await update_config()
        
        logger.info("✅ Миграция успешно завершена!")
        logger.info("Перезапустите сервер CRM для применения изменений.")
        
    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())