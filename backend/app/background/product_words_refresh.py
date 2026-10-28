"""Фоновая задача: раз в сутки обновляет materialized view product_words
(словарь слов каталога для исправления опечаток, см. app/services/
product_words_correction.py и миграцию w2x4y6z8a0b2_product_words_mv.py).

Тот же lifespan-паттерн, что у соседей app/background/deadline_reminders.py
и app/background/waybill_overdue.py (владелец, 28.10.2026, доработка «этап
0») — зовётся из app/startup/__init__.py::lifespan так же, asyncio.create_
task + cancel при остановке.

ПРАВИЛО №6 — ОДНА функция делает фактическое REFRESH (refresh_product_
words_if_stale с TTL-гейтом в product_words_correction.py); эта задача
просто дёргает её раз в сутки. Второй триггер — сразу после импорта
каталога — должен был бы звать ТУ ЖЕ функцию из единой точки импорта
(app/services/products_import_apply.py::apply_products_import), но этот
файл на момент доработки уже редактировался ДРУГОЙ параллельной сессией
(чужой необязанный diff) — чтобы не конфликтовать с ней, хук туда НЕ
добавлен в этом заходе; добавить его (одну строку вызова после `await db.
commit()` перед `return {...}`, см. структуру функции) — отдельная,
безопасная по времени задача."""
import asyncio
import logging


async def _product_words_refresh_loop():
    """Каждые REFRESH_TTL_SECONDS (сутки) — REFRESH MATERIALIZED VIEW
    CONCURRENTLY product_words. force=True здесь: у фонового цикла и так
    интервал сна равен TTL, повторная проверка TTL внутри избыточна —
    сам факт пробуждения цикла уже means "прошли сутки"."""
    from app.database import async_session as _async_session
    from app.services.product_words_correction import (
        REFRESH_TTL_SECONDS,
        refresh_product_words_if_stale,
    )

    log = logging.getLogger(__name__)
    while True:
        try:
            await asyncio.sleep(REFRESH_TTL_SECONDS)
            async with _async_session() as db:
                await refresh_product_words_if_stale(db, force=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("product_words_refresh_loop failed")
            await asyncio.sleep(60)
