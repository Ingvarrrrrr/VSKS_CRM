#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, '.')

from app.database import engine, Base, async_session
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.user import User
from app.auth.jwt import hash_password
from sqlalchemy import select, update

async def init_db():
    async with engine.begin() as conn:
        # Создаём все таблицы (включая новые)
        await conn.run_sync(Base.metadata.create_all)
    
    async with async_session() as session:
        # Субсидии 2026 года
        subsidies_2026 = [
            ("ДНР_2026", 2026, 30000000.0, "Субсидия на поддержку ДНР"),
            ("ЗО_2026", 2026, 25000000.0, "Субсидия на здравоохранение"),
            ("КОС_2026", 2026, 20000000.0, "Субсидия на космическую деятельность"),
            ("ЛНР_2026", 2026, 28000000.0, "Субсидия на поддержку ЛНР"),
            ("МинОбр_2026", 2026, 40000000.0, "Субсидия Министерства образования"),
            ("МинПрос_2026", 2026, 35000000.0, "Субсидия Министерства просвещения"),
            ("ФАДМ_2026", 2026, 22000000.0, "Субсидия Федерального агентства по делам молодёжи"),
            ("МинТруд_2026", 2026, 32000000.0, "Субсидия Министерства труда"),
        ]
        
        created_subsidies = []
        for name, year, budget, description in subsidies_2026:
            result = await session.execute(select(Subsidy).where(Subsidy.name == name))
            subsidy = result.scalar_one_or_none()
            if not subsidy:
                subsidy = Subsidy(
                    name=name,
                    year=year,
                    budget=budget,
                    description=description
                )
                session.add(subsidy)
                created_subsidies.append(subsidy)
        
        if created_subsidies:
            await session.commit()
            for sub in created_subsidies:
                await session.refresh(sub)
                print(f"Создана субсидия: {sub.name} (id={sub.id})")
        
        # Проверяем, есть ли субсидия по умолчанию (для обратной совместимости)
        result = await session.execute(select(Subsidy).where(Subsidy.name == "Патриотика 2025"))
        subsidy = result.scalar_one_or_none()
        if not subsidy:
            subsidy = Subsidy(
                name="Патриотика 2025",
                year=2025,
                budget=26128070.0,
                description="Субсидия на патриотическое воспитание"
            )
            session.add(subsidy)
            await session.commit()
            await session.refresh(subsidy)
            print(f"Создана субсидия: {subsidy.name} (id={subsidy.id})")
        else:
            print(f"Субсидия уже существует: {subsidy.name} (id={subsidy.id})")
        
        # Основная субсидия для категорий ФЭО (используем первую из 2026)
        result = await session.execute(select(Subsidy).where(Subsidy.name == "ДНР_2026"))
        main_subsidy = result.scalar_one_or_none() or subsidy
        
        # Обновляем существующие категории ФЭО, присваивая им subsidy_id
        result = await session.execute(select(FeoCategory).where(FeoCategory.subsidy_id == None))
        categories_without_subsidy = result.scalars().all()
        if categories_without_subsidy:
            for cat in categories_without_subsidy:
                cat.subsidy_id = main_subsidy.id
            await session.commit()
            print(f"Обновлено {len(categories_without_subsidy)} категорий с subsidy_id={main_subsidy.id}")
        
        # Добавляем демо-категории согласно новой иерархии
        # Уровень 1: Направления расходов
        level1_names = [
            "Техническое оснащение деятельности штаба",
            "Организация мероприятий",
            "Поддержка работы интернет-ресурса организации",
            "Оказание услуг по транспортировке и проживанию"
        ]
        level1_cats = []
        for name in level1_names:
            result = await session.execute(
                select(FeoCategory).where(
                    FeoCategory.subsidy_id == subsidy.id,
                    FeoCategory.level == 1,
                    FeoCategory.name == name
                )
            )
            existing = result.scalar_one_or_none()
            if not existing:
                cat = FeoCategory(
                    subsidy_id=subsidy.id,
                    level=1,
                    name=name,
                    appendix=None,
                    is_active=True
                )
                session.add(cat)
                level1_cats.append(cat)
        if level1_cats:
            await session.commit()
            for cat in level1_cats:
                await session.refresh(cat)
            print(f"Добавлено {len(level1_cats)} категорий уровня 1")
        
        # Для каждого направления добавляем типы расходов (уровень 2)
        # Здесь просто пример для первого направления
        if level1_cats:
            first_dir = level1_cats[0]  # Техническое оснащение
            level2_cat = FeoCategory(
                subsidy_id=subsidy.id,
                parent_id=first_dir.id,
                level=2,
                name="Техническое оснащение деятельности штаба",
                appendix="Прил. 2",
                is_active=True
            )
            session.add(level2_cat)
            await session.commit()
            await session.refresh(level2_cat)
            print(f"Добавлен тип расходов: {level2_cat.name} (appendix={level2_cat.appendix})")
        
        # Пользователь уже создан вручную, пропускаем
        print("Пользователь admin уже существует")
        
        print("Инициализация базы данных завершена.")

if __name__ == "__main__":
    asyncio.run(init_db())