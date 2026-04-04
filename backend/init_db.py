#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, '.')

from app.database import engine, Base, async_session
import app.models  # noqa: F401 — register all models for create_all
from app.models.subsidy import Subsidy
from app.models.user import User
from app.auth.jwt import hash_password
from sqlalchemy import select

async def init_db():
    async with engine.begin() as conn:
        # Создаём все таблицы (включая новые)
        await conn.run_sync(Base.metadata.create_all)
    
    async with async_session() as session:
        # ── Субсидии: сеем ТОЛЬКО при первом запуске (если в БД ещё нет ни одной)
        existing_count = (await session.execute(select(Subsidy))).scalars().first()
        if not existing_count:
            subsidies_seed = [
                ("Тестовая 1", 2026, 0.0, "Тестовая субсидия 1"),
                ("Тестовая 2", 2026, 0.0, "Тестовая субсидия 2"),
                ("Тестовая 3", 2026, 0.0, "Тестовая субсидия 3"),
                ("Тестовая 4", 2026, 0.0, "Тестовая субсидия 4"),
                ("Тестовая 5", 2026, 0.0, "Тестовая субсидия 5"),
                ("Тестовая 6", 2026, 0.0, "Тестовая субсидия 6"),
                ("Тестовая 7", 2026, 0.0, "Тестовая субсидия 7"),
                ("Тестовая 8", 2026, 0.0, "Тестовая субсидия 8"),
                ("Тестовая 9", 2026, 0.0, "Тестовая субсидия 9"),
            ]
            for name, year, budget, description in subsidies_seed:
                session.add(Subsidy(name=name, year=year, budget=budget, description=description))
            await session.commit()
            print(f"Первый запуск: создано {len(subsidies_seed)} субсидий.")
        else:
            print("Субсидии уже существуют — сидинг пропущен.")

        # ── Пользователь admin
        admin = (await session.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
        if not admin:
            session.add(User(username="admin", password_hash=hash_password("admin123"), role="admin", full_name="Администратор", is_email_confirmed=True))
            await session.commit()
            print("Создан пользователь admin.")
        else:
            print("Пользователь admin уже существует")
        
        print("Инициализация базы данных завершена.")

if __name__ == "__main__":
    asyncio.run(init_db())