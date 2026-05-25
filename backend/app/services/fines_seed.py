"""
fines_seed.py — Расширенный seed тестовых штрафов для Phase 29.3.

Создаёт 25 тестовых штрафов с разнообразием:
  - разные ТС (до 30 из working)
  - разные водители (fleet_role='driver', fallback — любые users)
  - разные типы нарушений и суммы (500–30 000 руб)
  - разные даты (последние 6 месяцев)
  - разные статусы: unpaid / paid / disputed
  - разные локации (города РФ)
  - номера постановлений

Идемпотентность:
  - force=False  → пропустить если уже >= target_count штрафов
  - force=True   → добавить поверх существующих (для пополнения демо-данных)

Запуск вручную:
  docker exec vsks_crm-backend-1 python -m app.services.fines_seed
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta

from sqlalchemy import select, func

from app.database import async_session
from app.models.vehicle_fine import VehicleFine
from app.models.vehicle import Vehicle
from app.models.user import User

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Справочники нарушений: (тип, сумма_руб, локация)
# ---------------------------------------------------------------------------

VIOLATIONS = [
    ("Превышение скорости 20-40 км/ч",          500,   "Москва, ул. Ленинградская, 12"),
    ("Превышение скорости 40-60 км/ч",           1000,  "Москва, МКАД 43-й км"),
    ("Превышение скорости 60-80 км/ч",           2500,  "Краснодар, ул. Красная, 56"),
    ("Превышение скорости более 80 км/ч",        5000,  "Ростов-на-Дону, пр. Ворошиловский, 3"),
    ("Проезд на запрещающий сигнал светофора",   1000,  "Москва, Садовое кольцо, д. 4"),
    ("Нарушение правил парковки",                1500,  "Санкт-Петербург, Невский пр., 15"),
    ("Стоянка в зоне действия запрещающего знака", 3000, "Новосибирск, ул. Вокзальная, 1"),
    ("Непредоставление преимущества пешеходу",   1500,  "Казань, ул. Кремлёвская, 22"),
    ("Выезд на полосу встречного движения",      5000,  "Екатеринбург, ул. Малышева, 68"),
    ("Разговор по телефону за рулём",            1500,  "Москва, ТТК, 5-й км"),
    ("Непристёгнутый ремень безопасности",       1000,  "Самара, ул. Молодогвардейская, 7"),
    ("Тонировка передних стёкол",                500,   "Волгоград, пр. Ленина, 10"),
    ("Проезд под кирпич",                        5000,  "Нижний Новгород, ул. Большая Покровская, 33"),
    ("Нарушение дорожной разметки",              500,   "Челябинск, пр. Победы, 90"),
    ("Эксплуатация ТС с неисправными тормозами", 1000,  "Красноярск, ул. Мира, 102"),
    ("Управление ТС без страхового полиса ОСАГО", 800,  "Уфа, ул. Ленина, 28"),
    ("Нарушение правил перевозки грузов",        3000,  "Пермь, шоссе Космонавтов, 111"),
    ("Выезд на встречную полосу на мосту",       5000,  "Воронеж, Чернавский мост"),
    ("Остановка под запрещающим знаком",         1500,  "Омск, ул. Ленина, 21"),
    ("Нарушение правил обгона",                  7500,  "Саратов, ул. Московская, 55"),
    ("Опасное вождение",                         15000, "Тюмень, ул. Республики, 90"),
    ("Управление ТС в состоянии алкогольного опьянения", 30000, "Москва, Рублёвское шоссе, 14"),
    ("Скрылся с места ДТП",                      25000, "Краснодар, ул. Гагарина, 77"),
    ("Превышение скорости 20-40 км/ч (повторно)", 1000, "Москва, МКАД 68-й км"),
    ("Непропуск транспортного средства с приоритетом", 5000, "Ростов-на-Дону, пр. Буденновский, 15"),
]

# Иногда генерируем суммы с вариацией (штрафы могут быть кратными)
AMOUNT_VARIANTS = [500, 800, 1000, 1500, 2500, 3000, 5000, 7500, 10000, 15000, 25000, 30000]

LOCATIONS_EXTRA = [
    "Москва, ул. Профсоюзная, 37",
    "Москва, Варшавское шоссе, 3",
    "Санкт-Петербург, ул. Гороховая, 12",
    "Ставрополь, пр. Карла Маркса, 77",
    "Краснодар, ул. Северная, 42",
]


async def seed_fines(target_count: int = 25, force: bool = False) -> dict:
    """
    Идемпотентный seed тестовых штрафов.

    Args:
        target_count: сколько штрафов создать.
        force: False → пропустить если уже >= target_count; True → добавить поверх.

    Returns:
        dict с ключами created / skipped / reason.
    """
    async with async_session() as db:
        # ── Проверка идемпотентности ──────────────────────────────────────────
        existing_count = await db.scalar(select(func.count()).select_from(VehicleFine))
        if not force and existing_count and existing_count >= target_count:
            msg = f"Штрафов уже {existing_count} >= {target_count}, seed пропущен (force=False)"
            log.info(f"fines_seed: {msg}")
            return {"reason": "already_seeded", "existing": existing_count}

        # ── Получить ТС ───────────────────────────────────────────────────────
        vehicles_q = await db.execute(
            select(Vehicle.id).where(Vehicle.state == "working").limit(30)
        )
        vehicle_ids = vehicles_q.scalars().all()

        if not vehicle_ids:
            # Fallback: любые ТС без фильтра по состоянию
            vehicles_q2 = await db.execute(select(Vehicle.id).limit(30))
            vehicle_ids = vehicles_q2.scalars().all()

        if not vehicle_ids:
            log.warning("fines_seed: нет ТС в БД — seed пропущен")
            return {"reason": "no_vehicles"}

        # ── Получить водителей ────────────────────────────────────────────────
        drivers_q = await db.execute(
            select(User.id).where(User.fleet_role == "driver").limit(20)
        )
        driver_ids = drivers_q.scalars().all()

        if not driver_ids:
            # Fallback: users с can_drive=True
            drv_q2 = await db.execute(
                select(User.id).where(User.can_drive == True).limit(20)
            )
            driver_ids = drv_q2.scalars().all()

        if not driver_ids:
            # Последний fallback: любые users
            any_q = await db.execute(select(User.id).limit(15))
            driver_ids = any_q.scalars().all()

        # ── Генерация штрафов ─────────────────────────────────────────────────
        random.seed(42)  # воспроизводимо
        now = datetime.utcnow()

        # Определяем сколько ещё нужно создать
        to_create = target_count if force else (target_count - (existing_count or 0))
        to_create = max(to_create, 0)

        fines = []
        for i in range(to_create):
            vehicle_id = random.choice(vehicle_ids)

            # 15% штрафов без привязки к водителю (ТС зафиксировано камерой)
            if driver_ids and random.random() > 0.15:
                driver_user_id = random.choice(driver_ids)
            else:
                driver_user_id = None

            # Дата нарушения — случайно за последние 6 месяцев
            days_ago = random.randint(1, 180)
            issued_at = now - timedelta(days=days_ago)

            # Тип нарушения и базовая сумма
            viol_type, base_amount, location = VIOLATIONS[i % len(VIOLATIONS)]

            # Иногда перекрываем сумму из AMOUNT_VARIANTS (20% случаев)
            if random.random() < 0.2:
                amount = random.choice(AMOUNT_VARIANTS)
            else:
                amount = base_amount

            # Статус: 50% unpaid, 35% paid, 15% disputed
            r = random.random()
            if r < 0.50:
                status = "unpaid"
                paid_at = None
            elif r < 0.85:
                status = "paid"
                paid_at = issued_at + timedelta(days=random.randint(3, 45))
            else:
                status = "disputed"
                paid_at = None

            # Номер постановления (18810177XXXXXXXX — формат ГИБДД)
            doc_number = f"18810177{random.randint(10000000, 99999999)}"

            # Комментарий для некоторых штрафов
            comment = None
            if status == "disputed":
                comment = "Оспаривается в ГИБДД. Водитель предоставил возражение."
            elif status == "paid" and random.random() < 0.3:
                comment = "Оплачено со скидкой 50% в течение 20 дней."

            fine = VehicleFine(
                vehicle_id=vehicle_id,
                driver_user_id=driver_user_id,
                violation_type=viol_type,
                amount=amount,
                issued_at=issued_at,
                location=location,
                status=status,
                paid_at=paid_at,
                doc_number=doc_number,
                comment=comment,
            )
            fines.append(fine)

        if fines:
            db.add_all(fines)
            await db.commit()

        result = {
            "created": len(fines),
            "existing_before": existing_count or 0,
            "vehicles_used": len(vehicle_ids),
            "drivers_used": len(driver_ids),
        }
        log.info(f"fines_seed: {result}")
        return result


if __name__ == "__main__":
    import sys

    force_flag = "--force" in sys.argv or "-f" in sys.argv
    asyncio.run(seed_fines(25, force=force_flag))
