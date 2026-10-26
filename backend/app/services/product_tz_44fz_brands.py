"""ЕДИНСТВЕННЫЙ загрузчик каталожного набора брендов для ТЗ 44-ФЗ (ревью
владельца 26.10.2026, п.1). ПРАВИЛО №6 — build_tz_44fz() (product_tz_44fz.py)
остаётся чистой функцией без обращений к БД; эта функция грузит набор ОДИН
раз (скрипт — один вызов на весь прогон; роутер — кешированно на процесс,
см. app/routers/products_tz44.py) и передаёт его параметром `brands`.

Набор = distinct Product.manufacturer (не NULL, длина >= 3) ОБЪЕДИНЁННЫЙ со
значениями характеристик «Бренд/Производитель/Торговая марка» (длина >= 3)
по ВСЕМ товарам каталога — не только у текущего товара (локальный бренд
конкретного товара собирает отдельно product_tz_44fz._collect_local_brand_words,
это другая, более дешёвая операция на один товар)."""
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.product_tz_44fz_rules import STOP_BRAND_WORDS

_BRAND_CHARACTERISTIC_NAME_PATTERN = "(бренд|производител|торговая марка|товарный знак|торговый знак)"


def _is_stop_brand_word(value: str) -> bool:
    """Ревью v2 (26.10.2026, п.1): цвета/материалы/страны/общие слова,
    которые поставщики по ошибке кладут в "Производитель"/"Бренд", не
    должны попадать в набор брендов — они потом выгрызают куски из
    ДРУГИХ значений ("алюминий-цинк" → "( -цинк)"). Сравнение по
    ПОЛНОМУ значению (а не по словам внутри) — "АВТОВАЗ Красный" как
    бренд целиком не стоп-слово, даже если содержит слово "красный"."""
    return value.strip().lower() in STOP_BRAND_WORDS


async def collect_catalog_brands(db: AsyncSession) -> frozenset:
    manufacturers = (await db.execute(sql_text(
        "SELECT DISTINCT manufacturer FROM products "
        "WHERE manufacturer IS NOT NULL AND length(trim(manufacturer)) >= 3"
    ))).scalars().all()

    # Фильтр на jsonb_typeof ПЕРЕД jsonb_array_elements (во вложенном
    # подзапросе) — set-returning функция иначе вызывается на каждой
    # строке ДО применения WHERE и падает на characteristics, которые не
    # являются JSON-массивом (NULL/объект/скаляр).
    characteristic_brands = (await db.execute(sql_text(
        """
        SELECT DISTINCT elem->>'value' AS brand
        FROM (
            SELECT characteristics FROM products
            WHERE characteristics IS NOT NULL
              AND jsonb_typeof(characteristics) = 'array'
        ) p, jsonb_array_elements(p.characteristics) AS elem
        WHERE elem->>'name' ~* :name_pattern
          AND length(trim(elem->>'value')) >= 3
        """
    ), {"name_pattern": _BRAND_CHARACTERISTIC_NAME_PATTERN})).scalars().all()

    brands = set()
    for value in list(manufacturers) + list(characteristic_brands):
        if not value:
            continue
        value = value.strip()
        if len(value) >= 3 and not _is_stop_brand_word(value):
            brands.add(value)
    return frozenset(brands)
