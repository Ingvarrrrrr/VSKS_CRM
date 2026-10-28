"""Исправление опечаток ПО СЛОВАМ каталога — шаг 4 лестницы поиска «как
помнит» (владелец, 28.10.2026, доработка «этап 0»). Единственный механизм
исправления опечаток (Правило №6) — заменяет старый trgm-fallback
`word_similarity(name, ...)` по ВСЕЙ строке названия (убран из
product_search.py): тот матчил посторонние товары («огнетушитель
порошковый 4 кг» находил кабели/автоматы — похожесть по ВСЕЙ строке
слишком грубая мера). Теперь — каждое НЕИЗВЕСТНОЕ слово запроса заменяется
на ближайшее слово словаря каталога (materialized view product_words, см.
миграцию w2x4y6z8a0b2) до того, как строить обычный FTS-запрос.

Обновление MV — НЕ на каждый поиск (дорогой скан каталога под
REFRESH ... CONCURRENTLY) — вызывается:
  1. раз в сутки из фонового цикла app/background/product_words_refresh.py
     (тот же lifespan-паттерн, что у app/background/deadline_reminders.py
     и соседей — app/startup/__init__.py);
  2. сразу после импорта каталога — app/services/products_import_apply.py
     ::apply_products_import — ЕДИНАЯ точка импорта файлов (Правило №6,
     второй «после импорта» хук не искали/не завели). Оба вызова идут через
     ОДНУ функцию refresh_product_words_if_stale с ОДНИМ TTL-гейтом
     (REFRESH_TTL_SECONDS) — серия импортов подряд не долбит REFRESH на
     каждый файл."""
from __future__ import annotations

import logging
import re
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# Раз в сутки — см. docstring модуля (REFRESH ... CONCURRENTLY на 250 тыс.
# строк — секунды, не миллисекунды, поэтому TTL такой же порядок, что и у
# "раз в сутки" задач app/background/*, а не как у 30-минутного кэша
# брендов get_manufacturer_brand_dictionary — там кэш в памяти процесса,
# здесь честный скан каталога).
REFRESH_TTL_SECONDS = 24 * 60 * 60

# similarity() >= порог — «тот же товар» ближайшее совпадение (владелец,
# 28.10.2026, задание: «порог ≥0.5, top-1»).
CORRECTION_SIMILARITY_THRESHOLD = 0.5

_last_refreshed_at: dict = {"ts": 0.0}

_WORD_RE = re.compile(r"^[a-zA-Zа-яёА-ЯЁ]{3,}$")


async def refresh_product_words_if_stale(db: AsyncSession, *, force: bool = False) -> bool:
    """REFRESH MATERIALIZED VIEW CONCURRENTLY product_words — не чаще
    REFRESH_TTL_SECONDS, если не force=True. CONCURRENTLY требует UNIQUE
    индекс (ix_product_words_word, см. миграцию) и не блокирует чтение
    словаря во время обновления. Возвращает True, если REFRESH реально
    выполнился (для тестов/замеров — отличить «пропущено по TTL» от
    «выполнено»)."""
    now = time.monotonic()
    if not force and (now - _last_refreshed_at["ts"]) < REFRESH_TTL_SECONDS:
        return False
    try:
        await db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY product_words"))
        await db.commit()
        _last_refreshed_at["ts"] = now
        return True
    except Exception:
        log.exception("product_words REFRESH failed")
        await db.rollback()
        return False


async def correct_unknown_words(db: AsyncSession, words: list[str]) -> dict[str, str]:
    """Для каждого слова (буквы, без цифр, >=3 символа) — если его НЕТ в
    product_words И есть похожее (similarity >= CORRECTION_SIMILARITY_
    THRESHOLD, top-1 по pg_trgm) — заменить. Возвращает {исходное:
    исправленное} ТОЛЬКО для реально заменённых слов (владелец, 28.10.2026,
    «этап 0», шаг 4). Слова КОРОЧЕ 3 букв / с цифрами не корректируются —
    словарь их не содержит (см. докстринг миграции), а 1-2-буквенные
    опечатки неотличимы от намеренно коротких слов."""
    corrections: dict[str, str] = {}
    seen: set[str] = set()
    for raw_word in words:
        wl = raw_word.lower()
        if wl in seen or not _WORD_RE.match(wl):
            continue
        seen.add(wl)
        exists = (await db.execute(
            text("SELECT 1 FROM product_words WHERE word = :w"), {"w": wl},
        )).first()
        if exists:
            continue
        row = (await db.execute(
            text(
                "SELECT word, similarity(word, :w) AS sim FROM product_words "
                "WHERE word % :w ORDER BY sim DESC LIMIT 1"
            ),
            {"w": wl},
        )).first()
        if row and row.sim >= CORRECTION_SIMILARITY_THRESHOLD and row.word != wl:
            corrections[raw_word] = row.word
    return corrections
