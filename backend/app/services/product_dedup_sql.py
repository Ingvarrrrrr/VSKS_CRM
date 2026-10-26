"""SQL-эквивалент app.product_matcher._normalize — ТОЛЬКО для серверной
группировки дублей в POST /api/products/deduplicate (владелец, 2026-10-26,
сужение каталога под рост до 250+ тыс. товаров).

ПРАВИЛО №5/№6 — почему это НЕ копия app.services.product_catalog_match
._sql_normalized_name_expr(): та формула (translate() по _CHAR_FOLD_MAP) —
единая точка для ТОЧНОГО сопоставления импорта (гомоглифы кириллица/латиница,
цифро-буквенные двойники, НЕ трогает пунктуацию). Дедуп каталога — другая,
уже существующая (и явно отдельная от неё, см. докстринг
app/routers/products_match.py::deduplicate_products) нормализация:
app.product_matcher._normalize — NFKC + lower() + ё→е + ВЫРЕЗАНИЕ пунктуации
(класс _PUNCT) заменой на пробел + схлопывание пробелов. У дедупа и импорта
разные источники истины ровно потому, что это две раздельные задачи
(«слить идентичные записи каталога» vs «не завести дубль при импорте»), а не
один показатель — заводить общую формулу между ними значило бы менять
поведение одной из задач, не санкционированное владельцем.

Здесь — SQL-ВЕРСИЯ ТОЙ ЖЕ _normalize (посимвольно translate(), как и Python
.sub() на одиночные символы _PUNCT) — чтобы GROUP BY считался в БД, а не
тащил весь каталог в Python ради построения union-find. NFKC-нормализацию
Postgres не воспроизводит (нет built-in NFKC) — риск: строка с
NFKC-компонуемыми составными символами (напр. редкие комбинирующие
диакритики) может дать в SQL-ключе состояние ДО свёртки, тогда как Python
даёl ПОСЛЕ неё. На кириллическом/латинском тексте без диакритики (боевой
каталог) NFKC — no-op, расхождение проверено скриптом сравнения чисел групп
на живой БД (см. отчёт сессии, backend/tests/test_products_catalog_scale.py).

GROUP BY по этому выражению без индекса — seq scan по всей таблице
(владелец, 2026-10-26, замер на 250к). Функциональный B-tree индекс под
ТОЧНО это выражение — в backend/alembic/versions/
r5s7u9w1y3a5_product_search_indexes.py::ix_products_dedup_normalized_name.
Единый источник символов — `_from_to_chars()` ниже: и ORM-выражение
(`sql_dedup_normalized_name_expr`), и SQL-текст для CREATE INDEX
(`dedup_normalized_name_sql_text`) строятся из одного и того же кортежа
(Правило №6 — не плодить второй литерал тех же символов). Что они на самом
деле дают одинаковый результат проверяет
backend/tests/test_product_dedup_sql_index_matches.py — выполняет оба
варианта (ORM-запрос и raw SQL с текстом индекса) на одних строках в живой
БД и сравнивает ключи, а не сравнивает скомпилированный текст (SQLAlchemy
literal_binds экранирует '%' под paramstyle драйвера — текстовое сравнение
даёт ложные расхождения)."""
from sqlalchemy import func

from app.models.product import Product

# Тот же набор символов, что app.product_matcher._PUNCT (вырезаются →
# заменяются пробелом, ПОСИМВОЛЬНО — как Python re.sub на одиночные символы
# класса, не как substring-паттерн).
_PUNCT_CHARS = "\"'«»()[],.;:!?@#%&*=+/\\—–-_…"


def _from_to_chars() -> tuple[str, str]:
    """Единственный источник пар (откуда → куда) для translate() — и ORM-
    выражения, и текста индекса (см. докстринг модуля)."""
    return _PUNCT_CHARS + "ё", (" " * len(_PUNCT_CHARS)) + "е"


def sql_dedup_normalized_name_expr():
    """SQL-ключ группировки дублей — см. докстринг модуля. lower() ПЕРЕД
    остальным (как Python: NFKC→lower()→ё-замена→вырезание пунктуации), затем
    своя таблица translate() (пунктуация→пробел, Ё по верхнему регистру — на
    случай, если lower() применить ПОСЛЕ translate; здесь lower идёт первым,
    поэтому 'Ё' уже стала 'ё' и остаётся свернуть именно нижний регистр — см.
    ниже вторым translate-проходом), затем схлопывание пробелов + trim."""
    from_chars, to_chars = _from_to_chars()
    lowered = func.lower(Product.name)
    # После lower() 'Ё'→'ё' уже случилось — заменяем нижнерегистровую 'ё'→'е'
    # ОДНИМ translate() вместе с вырезанием пунктуации (один проход, как и
    # Python делает это двумя .replace/.sub, но результат идентичен порядку
    # операций, т.к. пунктуация и 'ё' не пересекаются).
    folded = func.translate(lowered, from_chars, to_chars)
    collapsed = func.regexp_replace(func.trim(folded), r"\s+", " ", "g")
    return collapsed


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def dedup_normalized_name_sql_text(column_ref: str = "name") -> str:
    """Та же формула в виде SQL-текста — для CREATE INDEX в миграции
    r5s7u9w1y3a5 (ПРАВИЛО №6: один источник символов — `_from_to_chars()`,
    не второй литерал той же формулы). `column_ref` — "name" в индексе
    (колонка индексируемой таблицы без схемы/алиаса — как того требует
    Postgres для функциональных индексов)."""
    from_chars, to_chars = _from_to_chars()
    return (
        f"regexp_replace(trim(translate(lower({column_ref}), "
        f"{_sql_quote(from_chars)}, {_sql_quote(to_chars)})), '\\s+', ' ', 'g')"
    )
