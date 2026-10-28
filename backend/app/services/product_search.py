"""Единый механизм серверного поиска/фильтров каталога товаров (Правило №6).

Повод: каталог products на проде — 53 797 строк, растёт к 250+ тыс.
GET /api/products/ без limit отдавал ВЕСЬ каталог целиком. Это ОДИН сервис,
которым пользуются страница «Товары» (GET /api/products/page), совместимость
со старым списком (GET /api/products/ без ids) и, позже, пикер товара в
закупке/сужение кандидатов в /products/match — вторую реализацию поиска не
писать (Правило №6), звать build_product_search_query/search_products отсюда.

Поиск многословный: запрос режется на слова по пробелам, КАЖДОЕ слово должно
найтись (AND) ILIKE '%слово%' по name/article/manufacturer (+ description —
только при search_description=True, см. docstring миграции
r5s7u9w1y3a5_product_search_indexes.py почему description без индекса по
умолчанию). % _ \ в словах экранируются — иначе пользовательский ввод ломает
паттерн LIKE. ё/е НЕ нормализуются отдельно здесь — это интерактивный ILIKE-
поиск по сырым данным (как и раньше в list_products), а не точное
сопоставление дублей (та нормализация — только в
app/services/product_catalog_match.py, Правило №6, не плодим второй
нормализатор для другой задачи).

Ранжирование при search (без явного sort): точное совпадение имени (без
регистра) → имя начинается с запроса → similarity(name, запрос) по убыванию
→ name. Без search — sort по белому списку колонок (SORTABLE_COLUMNS),
default 'name' asc.

ГИБРИДНОЕ РАНЖИРОВАНИЕ широких запросов (владелец, 26.10.2026, доработка):
полная формула выше (similarity по ВСЕМ совпадениям) требует прочитать и
отсортировать КАЖДУЮ строку-кандидата — для частых слов ("кабель" из 24 тыс.
товаров, но и "кб" из 1050 — границы по числу совпадений ненадёжны, 1050
совпадений уже стоили 288мс) это не укладывается в 200мс. С
RANK_FULL_THRESHOLD(500)+ совпадений ранжирование идёт ДВУМЯ группами без
similarity вообще — см. _fetch_hybrid_page ниже и докстрин там, почему
именно range-условие по lower(name) (не LIKE), почему убран
max_parallel_workers_per_gather и почему есть HYBRID_OFFSET_LIMIT_CAP.

total/total_capped: total — ТОЧНЫЙ count(*) по тем же условиям, без потолка
(владелец, 26.10.2026: счётчик всегда точный). total_capped оставлено в
сигнатуре count_products/search_products и ответе API для совместимости —
всегда False.

stale_only/stale_total — читают app/services/price_freshness_sql.py
::stale_condition (тот же источник правды, что price_freshness.evaluate,
см. докстринг там).
"""
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from sqlalchemy import Select, and_, case, func, literal, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.models.product import Product
from app.services.price_freshness import FreshnessContext
from app.services.price_freshness_sql import apply_stale_join
from app.services.product_query_parse import ParsedQuery, get_manufacturer_brand_dictionary, parse_query
from app.services.product_words_correction import correct_unknown_words

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_IDS = 500

# Гибридное ранжирование (владелец, 26.10.2026, доработка): выше этого числа
# совпадений similarity-ранжирование по ВСЕМ строкам не укладывается в
# 200мс (замер на 263 тыс. товаров: "кб" — 1050 совпадений — 288мс, "ДКС" —
# 8980 — 187мс, т.е. граница по числу совпадений ненадёжна и ниже 2000 —
# порог взят с запасом в меньшую сторону, а не замерен ровно по границе).
RANK_FULL_THRESHOLD = 500

# Суммарно (offset+limit) строк, которые ГИБРИДНЫЙ путь обязан прочитать по
# индексу (lower(name),id) ОДНИМ Index Scan без Sort — см. докстринг
# _fetch_hybrid_page. Выше этого порога планировщик PostgreSQL на 263 тыс.
# строк (замер) путает оценку кардинальности range-условия по lower(name) и
# САМ переключается на другой (на порядок медленнее — 850мс против 15мс на
# том же запросе) индекс/план — 6000 взято с запасом от замеренной границы
# ~8 тыс. (и заведомо покрывает offset=5000 + limit<=200, реалистичную
# глубину пагинации внутри широкого запроса). За этим порогом — редкий
# случай, откатываемся на медленный, но корректный full-ranking путь.
HYBRID_OFFSET_LIMIT_CAP = 6_000

# Белый список колонок сортировки без search (Правило №8 п.6 — вход
# валидируется ДО запроса в БД, значение вне списка → 422 вызывающей
# стороной, НЕ 500 при попытке ORDER BY произвольной строкой).
SORTABLE_COLUMNS = {
    "name": Product.name,
    "category": Product.category,
    "product_type": Product.product_type,
    "price": Product.price,
    "price_updated_at": Product.price_updated_at,
    "updated_at": Product.updated_at,
    "id": Product.id,
}

_LIKE_ESCAPE_CHARS = ("\\", "%", "_")


def _escape_like(word: str) -> str:
    """Экранирует спецсимволы ILIKE (\\ % _) в слове поиска — иначе
    пользовательский ввод ломает паттерн или матчит произвольные символы."""
    out = word
    for ch in _LIKE_ESCAPE_CHARS:
        out = out.replace(ch, "\\" + ch)
    return out


def _search_words(search: str) -> list[str]:
    return [w for w in search.strip().split() if w]


# Слова короче этого числа символов pg_trgm НЕ индексирует (нужно минимум 3
# символа на триграмму) — ILIKE '%слово%' по такому слову уходит в seq scan
# по всему каталогу (замер владельца, 26.10.2026: 2с на 250 тыс. строк).
MIN_TRIGRAM_WORD_LEN = 3


def _all_words_too_short_for_trigram(search: str) -> bool:
    """True, когда ВСЕ слова запроса короче MIN_TRIGRAM_WORD_LEN — в этом
    случае ILIKE-поиск по словам заменяется на startswith по индексу
    ix_products_name_lower_id (см. _startswith_condition), а не отключается
    фильтр вовсе."""
    words = _search_words(search)
    return bool(words) and all(len(w) < MIN_TRIGRAM_WORD_LEN for w in words)


def _word_condition(word: str, *, search_description: bool):
    pattern = f"%{_escape_like(word)}%"
    cols = [Product.name, Product.article, Product.manufacturer]
    if search_description:
        cols.append(Product.description)
    return or_(*(col.ilike(pattern) for col in cols))


@dataclass
class ProductSearchFilters:
    search: Optional[str] = None
    search_description: bool = False
    feo_category_id: Optional[int] = None
    category: Optional[Sequence[str]] = None
    product_type: Optional[Sequence[str]] = None
    is_active: Optional[bool] = None
    price_min: Optional[Decimal] = None
    price_max: Optional[Decimal] = None
    stale_only: bool = False
    sort: str = "name"
    order: str = "asc"


def _apply_non_search_filters(q: Select, f: ProductSearchFilters, freshness_ctx: Optional[FreshnessContext]) -> Select:
    """Все фильтры КРОМЕ самого текста поиска (category/product_type/
    is_active/price/stale_only) — вынесено отдельно от _apply_filters, т.к.
    гибридному ранжированию (_fetch_hybrid_page) группа А (имя начинается с
    запроса) не нужно повторно накладывать word-условие поиска: startswith
    всей фразой ЛОГИЧЕСКИ ВКЛЮЧАЕТ containment той же фразы (Правило №6 —
    одно условие, не два эквивалентных в разных местах)."""
    if f.feo_category_id is not None:
        q = q.where(Product.feo_category_id == f.feo_category_id)
    if f.category:
        q = q.where(Product.category.in_(list(f.category)))
    if f.product_type:
        q = q.where(Product.product_type.in_(list(f.product_type)))
    if f.is_active is not None:
        q = q.where(Product.is_active == f.is_active)
    if f.price_min is not None:
        q = q.where(Product.price >= f.price_min)
    if f.price_max is not None:
        q = q.where(Product.price <= f.price_max)
    if f.stale_only:
        if freshness_ctx is None:
            raise ValueError("stale_only требует freshness_ctx (price_freshness.load_context)")
        # apply_stale_join добавляет ОДИН LATERAL-join к fx_rates (а не
        # восемь коррелированных подзапросов на строку — замер 50с на 263
        # тыс. товаров до фикса, см. докстринг price_freshness_sql.py).
        q, cond = apply_stale_join(q, freshness_ctx)
        q = q.where(cond)
    return q


def _apply_filters(q: Select, f: ProductSearchFilters, freshness_ctx: Optional[FreshnessContext]) -> Select:
    q = _apply_non_search_filters(q, f, freshness_ctx)
    if f.search:
        if _all_words_too_short_for_trigram(f.search):
            # Все слова короче 3 символов — pg_trgm их не индексирует,
            # ILIKE '%слово%' был бы seq scan. Вместо containment — startswith
            # по индексу ix_products_name_lower_id (см. MIN_TRIGRAM_WORD_LEN).
            q = q.where(_startswith_condition(f))
        else:
            words = _search_words(f.search)
            for word in words:
                q = q.where(_word_condition(word, search_description=f.search_description))
    return q


def _prefix_upper_bound(prefix: str) -> Optional[str]:
    """Следующая строка после ВСЕХ строк с данным префиксом — инкремент
    последнего кодпойнта на 1 (та же идея, что Postgres сам применяет для
    LIKE 'prefix%' на pattern-индексах, см. докстринг _fetch_hybrid_page).
    None — вырожденный случай (последний символ — U+10FFFF, максимальный
    Unicode кодпойнт, в реальных поисковых запросах не встречается):
    вызывающая сторона обязана подстраховаться доп. фильтром LIKE."""
    if not prefix:
        return None
    head, last = prefix[:-1], prefix[-1]
    cp = ord(last)
    if cp >= 0x10FFFF:
        return None
    return head + chr(cp + 1)


def _startswith_condition(filters: "ProductSearchFilters"):
    """Условие «имя начинается с запроса без учёта регистра» — ПРОСТОЕ
    range-условие (>=, <) по умолчательной коллации, а не LIKE 'prefix%'.

    Причина (владелец, 26.10.2026, замер на 263 тыс. товаров): с LIKE —
    даже через функциональный индекс (lower(name), id) с операторным классом
    text_pattern_ops ИЛИ default — PostgreSQL ошибается в оценке
    кардинальности составного условия (range + LIKE-дубль) и выбирает ПЛОХОЙ
    план (полный скан вместо точечного Index Scan, 650-890мс вместо единиц
    мс на том же запросе). Чистое range-условие (без LIKE) планировщик
    оценивает верно и уходит в Index Scan по ix_products_name_lower_id
    (см. миграцию) без отдельной сортировки — это и даёт <1мс вместо
    сотен мс. Корректность эквивалентности range==LIKE проверена на всём
    каталоге (263 тыс. строк, 0 расхождений) и тестом
    test_startswith_range_matches_like в test_product_search.py.
    """
    lo = filters.search.strip().lower()
    hi = _prefix_upper_bound(lo)
    cond = func.lower(Product.name) >= lo
    if hi is not None:
        cond = cond & (func.lower(Product.name) < hi)
    else:
        cond = cond & func.lower(Product.name).like(f"{_escape_like(lo)}%")
    return cond


def build_product_search_query(
    *,
    filters: ProductSearchFilters,
    freshness_ctx: Optional[FreshnessContext] = None,
    defer_characteristics: bool = True,
) -> Select:
    """Строит SELECT с WHERE/ORDER BY по фильтрам — используется и для
    выборки страницы результатов, и (с заменой select-колонки на count())
    для подсчёта total в search_products."""
    q = select(Product)
    if defer_characteristics:
        q = q.options(defer(Product.characteristics))
    q = _apply_filters(q, filters, freshness_ctx)

    if filters.search:
        if _all_words_too_short_for_trigram(filters.search):
            # Все результаты тут и так startswith (см. _apply_filters) —
            # similarity() по короткому слову не индексируется и не нужна,
            # сортируем по тому же (lower(name), id), что отдаёт индекс
            # ix_products_name_lower_id без отдельного узла Sort.
            q = q.order_by(func.lower(Product.name).asc(), Product.id.asc())
        else:
            norm_search = filters.search.strip().lower()
            exact_rank = case((func.lower(Product.name) == norm_search, 0), else_=1)
            startswith_rank = case((func.lower(Product.name).like(f"{_escape_like(norm_search)}%"), 0), else_=1)
            similarity_rank = func.similarity(Product.name, filters.search.strip())
            q = q.order_by(exact_rank, startswith_rank, similarity_rank.desc(), Product.name)
    else:
        sort_col = SORTABLE_COLUMNS.get(filters.sort, Product.name)
        if filters.order == "desc":
            q = q.order_by(sort_col.desc(), Product.id.desc())
        else:
            q = q.order_by(sort_col.asc(), Product.id.asc())
    return q


async def count_products(
    db: AsyncSession,
    filters: ProductSearchFilters,
    freshness_ctx: Optional[FreshnessContext] = None,
) -> tuple[int, bool]:
    """Возвращает (total, total_capped). total — ТОЧНЫЙ count(*) по тем же
    условиям, без потолка (владелец, 26.10.2026: счётчик всегда точный —
    раньше частые слова поиска отдавали «10 000+» вместо реального числа).
    total_capped оставлено в сигнатуре для совместимости вызывающих мест
    (search_products, роуты) и ответа API — всегда False."""
    inner = select(Product.id)
    inner = _apply_filters(inner, filters, freshness_ctx)
    inner = inner.subquery()
    q = select(func.count()).select_from(inner)
    total = (await db.execute(q)).scalar_one()
    return total, False


async def count_stale_products(db: AsyncSession, freshness_ctx: FreshnessContext) -> int:
    """Сколько товаров требуют актуализации во ВСЁМ каталоге, без учёта
    остальных фильтров — для бейджа на странице «Товары» (ПРАВИЛО №6: тот же
    stale_condition, что и stale_only в фильтрах). Вызывается БЕЗУСЛОВНО на
    каждый GET /api/products/page (products_page.py) — ОБЯЗАН идти через
    apply_stale_join (см. докстринг price_freshness_sql.py: без него это
    было ~50 секунд на 263 тыс. товаров)."""
    q, cond = apply_stale_join(select(func.count(Product.id)), freshness_ctx)
    q = q.where(cond)
    return (await db.execute(q)).scalar_one()


async def _fetch_hybrid_page(
    db: AsyncSession,
    filters: ProductSearchFilters,
    freshness_ctx: Optional[FreshnessContext],
    *,
    limit: int,
    offset: int,
) -> list[Product]:
    """Гибридное ранжирование широких запросов (владелец, 26.10.2026,
    доработка) — без similarity() по всем совпадениям. Вместо одной сортировки
    по (exact, startswith, similarity) — ДВЕ группы, каждая читается по
    индексу БЕЗ сортировки всего множества:
      А. имя начинается с запроса (без регистра) — _startswith_condition(),
         ORDER BY lower(name), id — индекс ix_products_name_lower_id
         (функциональный, DEFAULT operator class — НЕ text_pattern_ops, см.
         докстринг _startswith_condition, почему именно так) отдаёт эти
         строки УЖЕ в нужном порядке, без отдельного Sort-узла;
      Б. остальные совпадения (то же WHERE, что у полного ранжирования,
         минус группа А) — ORDER BY name, id — существующий
         ix_products_name_id, тоже без Sort (см. замер в докстринге
         миграции r5s7u9w1y3a5).
    Страница собирается здесь, в Python: сперва limit/offset применяются к
    А; если А вернула ровно `limit` строк — это весь ответ. Если меньше
    (k < limit) — группа А кончилась РОВНО на (offset+k)-й строке (видно по
    тому, что Index Scan её исчерпал), остаток добираем из Б с offset=0.
    Если А вернула 0 строк — offset ушёл ЗА пределы А, но насколько именно
    неизвестно без отдельного запроса — считаем точный размер А (та же
    ORDER BY lower(name), id LIMIT offset+1, см. HYBRID_OFFSET_LIMIT_CAP
    ниже, почему safe) и смещаем offset в Б.

    `SET LOCAL max_parallel_workers_per_gather = 0` — ОБЯЗАТЕЛЕН перед этими
    запросами (замер: с параллельным планом PostgreSQL на 263 тыс. строк
    выбирает Parallel Index Only Scan по ДРУГОМУ индексу — ix_products_name_id
    с Filter вместо Index Cond — и уходит в фактически полный скан, 170-280мс
    вместо <1мс на том же запросе без параллелизма). LOCAL — откатывается
    сам в конце транзакции запроса, другие запросы сессии не затрагивает.

    HYBRID_OFFSET_LIMIT_CAP — на 263 тыс. строк выше ~6-8 тыс. суммарно
    нужных строк (offset+limit, и то же для подсчёта точного размера А при
    k=0) PostgreSQL СНОВА путает оценку кардинальности range-условия и
    переключается на тот же плохой план — вызывающая сторона (search_products)
    обязана проверить offset+limit <= HYBRID_OFFSET_LIMIT_CAP ДО вызова этой
    функции и откатиться на build_product_search_query для глубокой
    пагинации (редкий случай, корректность не страдает, только скорость).

    ВАЖНО: SET LOCAL живёт до конца ТРАНЗАКЦИИ, не до конца запроса — в
    FastAPI один HTTP-запрос обычно = одна транзакция AsyncSession, значит
    без явного сброса max_parallel_workers_per_gather=0 просочился бы во
    ВСЕ следующие запросы той же транзакции (count_products, постобработку
    и т.п.), замедляя их без всякой пользы. Поэтому в конце — ВСЕГДА (even
    on exception) возвращаем DEFAULT через try/finally."""
    cond_a = _startswith_condition(filters)
    lower_name = func.lower(Product.name)

    def _qa(entity):
        q = select(entity).where(cond_a)
        return _apply_non_search_filters(q, filters, freshness_ctx)

    def _qb(entity):
        q = select(entity).where(~cond_a)
        return _apply_filters(q, filters, freshness_ctx)

    await db.execute(text("SET LOCAL max_parallel_workers_per_gather = 0"))
    try:
        qa_rows = _qa(Product).options(defer(Product.characteristics)).order_by(lower_name.asc(), Product.id.asc())
        rows_a = list((await db.execute(qa_rows.limit(limit).offset(offset))).scalars().all())

        if len(rows_a) == limit:
            return rows_a

        k = len(rows_a)
        if k > 0:
            # А закончилась ровно на (offset+k) — видно без доп. запроса.
            b_offset, b_limit = 0, limit - k
        else:
            qa_count = _qa(Product.id).order_by(lower_name.asc(), Product.id.asc())
            a_ids = (await db.execute(qa_count.limit(offset + 1))).scalars().all()
            total_a = len(a_ids)
            b_offset, b_limit = max(offset - total_a, 0), limit

        qb_rows = _qb(Product).options(defer(Product.characteristics)).order_by(Product.name.asc(), Product.id.asc())
        rows_b = list((await db.execute(qb_rows.limit(b_limit).offset(b_offset))).scalars().all())
        return rows_a + rows_b
    finally:
        await db.execute(text("SET LOCAL max_parallel_workers_per_gather = DEFAULT"))


# ---------------------------------------------------------------------------
# «Этап 0» — поиск по фразе «как помнит» (владелец, 28.10.2026, доработка
# ревью того же дня): встроенный полнотекстовый поиск PostgreSQL
# (to_tsvector('russian', ...) — стемминг русских окончаний средствами
# Postgres, не ручной обрезкой) + pg_trgm для опечаток — ТЕПЕРЬ для ЛЮБОГО
# многословного/словарного запроса (не только когда parse_query() находит
# специфичный признак), см. _looks_like_article_query ниже про единственное
# исключение. Повод ревью: «болгарка», «огнетушителя» (словоформа), «кабель
# медный в изоляции» (лишние слова) должны находиться стеммером/ранжированием,
# а не старым AND по КАЖДОМУ слову — ради этого этап и затевался.
#
# required-токены → AND в tsquery('russian', ...) — ТОЛЬКО текстовые (вид
# товара/бренд/прочие значимые слова, когда ParsedQuery.required пуст — см.
# search_products, «повышение» optional→required целиком, иначе остался бы
# десяток несвязанных слов без единого обязательного — расхождение со старым
# строгим AND для полностью нераспознанных фраз); цифровые/модельные/величины
# — ОТДЕЛЬНЫЙ пост-фильтр по регулярке через оператор ~* (word-boundary,
# "125" ≠ "1250"), т.к. русский стеммер Postgres цифры не понимает. У
# ПОСЛЕДНЕГО текстового required-токена — префикс `:*` (поиск по мере
# ввода). optional-токены → OR в tsquery, ТОЛЬКО для ts_rank-бонуса
# ранжирования, ничего не исключают.
#
# ВЫРАЖЕНИЕ _FTS_DOC_SQL ОБЯЗАНО текстуально совпадать с индексом в миграции
# f3t5s7q9u1e3_product_fts_index.py (Правило №6, один источник формулы) —
# иначе планировщик не свяжет запрос с GIN-индексом ix_products_fts (сверено
# EXPLAIN ANALYZE, см. отчёт сессии).
# ---------------------------------------------------------------------------

_SINGLE_TOKEN_WITH_DIGIT_RE = re.compile(r"^\S*\d\S*$")

# QA-находка (владелец, 28.10.2026): search="%%%" (ни буквы, ни цифры) шёл в
# «повысить optional→required», required становился из символов, которые
# _tsquery_word/численный фильтр целиком вычищают → ПУСТОЕ условие →
# запрос без WHERE по тексту → вся таблица (26 349). Защита ниже — до
# построения FTS-запроса.
_HAS_LETTER_OR_DIGIT_RE = re.compile(r"[0-9a-zA-Zа-яёА-ЯЁ]")


def _has_letter_or_digit(raw: str) -> bool:
    return bool(_HAS_LETTER_OR_DIGIT_RE.search(raw))


def _required_has_usable_token(required: list) -> bool:
    """После «повышения» optional→required (см. search_products) токены
    могут оказаться чистым мусором (операторы tsquery, одни знаки) —
    _tsquery_word вычищает их в пустую строку, а цифр там нет. Если ни
    один required-токен не даёт ни цифры, ни непустого текста после
    очистки — строить FTS-запрос БЕЗ единого реального условия нельзя
    (найдёт всё/ничего не осмысленно) — уходим на легаси-путь напрямую."""
    for tok in required:
        if any(ch.isdigit() for ch in tok):
            return True
        if _tsquery_word(tok).strip():
            return True
    return False


def _looks_like_article_query(raw: str) -> bool:
    """Один токен (без пробелов) с хотя бы одной цифрой — похоже на
    артикул/код производителя (владелец, 28.10.2026, ревью «этап 0»): такие
    запросы остаются на старом containment-пути (ILIKE across name/
    article/manufacturer, build_product_search_query/_fetch_hybrid_page)
    — «не ухудшить» существующее поведение поиска по артикулу/коду. Коды —
    не словарные слова, русский стеммер им не нужен и может быть хуже
    (коды иногда СОВПАДАЮТ с обычными словами после агрессивной нормализации
    стеммера — не проверено, не рискуем)."""
    words = raw.split()
    return len(words) == 1 and bool(_SINGLE_TOKEN_WITH_DIGIT_RE.match(words[0]))

_FTS_DOC_SQL = (
    "to_tsvector('russian', coalesce(name,'') || ' ' || "
    "coalesce(manufacturer,'') || ' ' || coalesce(article,''))"
)

# Слово «как есть» могло прийти с пользовательским вводом — для to_tsquery
# держим только буквы/цифры/пробелы/дефис (операторы tsquery & | ! : ( ) '
# из пользовательского текста ВСЕГДА вычищаются, см. _tsquery_word).
_TSQUERY_SAFE_RE = re.compile(r"[^0-9a-zA-Zа-яёА-ЯЁ\s-]")


def _tsquery_word(word: str) -> str:
    return _TSQUERY_SAFE_RE.sub(" ", word).strip()


def _tsquery_token(token: str, *, prefix: bool) -> Optional[str]:
    """required/optional-токен (может быть из нескольких слов — напр. бренд
    "Security Force") → фрагмент синтаксиса tsquery, слова токена через &.
    prefix=True — у ПОСЛЕДНЕГО слова токена ставится :* (поиск по мере
    ввода)."""
    words = [w for w in _tsquery_word(token).split() if w]
    if not words:
        return None
    parts = [f"{w}:*" if prefix and i == len(words) - 1 else w for i, w in enumerate(words)]
    return " & ".join(parts)


_VISCOSITY_NORM_RE = re.compile(r"^(\d+)([a-zа-яёA-ZА-ЯЁ])-(\d+)$")
_QUANTITY_NORM_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s+(\S+)$")


def _numeric_token_regex(token: str) -> str:
    """required-токен с цифрой (из product_query_parse.parse_query) →
    POSIX-regex для оператора ~* с границей числа — «125» не должно найти
    «1250» (владелец, 28.10.2026). Три формы ровно те, что строит parse_query:
    вязкость («5W-40»), величина с единицей («4 л»), голый цифровой/
    модельный код («125», составной «код·буква» из product_name_signature)."""
    m = _VISCOSITY_NORM_RE.match(token)
    if m:
        num1, letter, num2 = m.groups()
        return rf"(?<!\d){re.escape(num1)}{re.escape(letter)}-?{re.escape(num2)}(?!\d)"
    m = _QUANTITY_NORM_RE.match(token)
    if m:
        num, unit = m.groups()
        return rf"(?<!\d){re.escape(num)}\s*{re.escape(unit)}(?!\w)"
    core = token.replace("·", "")
    return rf"(?<![0-9a-zа-яёA-ZА-ЯЁ]){re.escape(core)}(?![0-9a-zа-яёA-ZА-ЯЁ])"


def _split_required_tokens(required: list) -> tuple[list[str], list[str]]:
    text_tokens, numeric_tokens = [], []
    for tok in required:
        if any(ch.isdigit() for ch in tok):
            numeric_tokens.append(tok)
        else:
            text_tokens.append(tok)
    return text_tokens, numeric_tokens


def _numeric_condition(token: str):
    pattern = _numeric_token_regex(token)
    return or_(
        Product.name.op("~*")(pattern),
        Product.article.op("~*")(pattern),
        Product.manufacturer.op("~*")(pattern),
    )


_BARE_NUMBER_RE = re.compile(r"^(\d+)")


def _bare_number(token: str) -> Optional[str]:
    """Голое число из цифрового/модельного/величина-токена («4 кг»→«4»,
    «125»→«125», «5W-40»→«5») — для «ослабленного» ранжирования шага 2
    (владелец, 28.10.2026, «этап 0», доработка): когда точный numeric-
    фильтр (границы единицы/формата) НИЧЕГО не нашёл, но число САМО ПО
    СЕБЕ где-то в тексте есть — это «похоже», ранжируем выше."""
    m = _BARE_NUMBER_RE.match(token)
    return m.group(1) if m else None


async def _fetch_fts_page(
    db: AsyncSession,
    filters: ProductSearchFilters,
    parsed: ParsedQuery,
    *,
    limit: int,
    offset: int,
    freshness_ctx: Optional[FreshnessContext],
    apply_numeric: bool = True,
) -> tuple[list[Product], int]:
    """apply_numeric=False — «ослабленный» шаг 2 лестницы (владелец,
    28.10.2026, доработка): цифровые/величина-токены НЕ фильтруют (WHERE),
    только мягко поднимают ранг, если голое число (_bare_number) где-то
    встретилось — «Огнетушитель порошковый ОП-2» находится по «огнетушитель
    порошковый 4 кг», когда точного «4 кг» в тексте нет."""
    text_tokens, numeric_tokens = _split_required_tokens(parsed.required)

    required_parts = []
    for i, tok in enumerate(text_tokens):
        part = _tsquery_token(tok, prefix=(i == len(text_tokens) - 1))
        if part:
            required_parts.append(part)
    required_tsquery = " & ".join(f"({p})" for p in required_parts) if required_parts else None

    optional_parts = [p for p in (_tsquery_token(t, prefix=False) for t in parsed.optional) if p]
    optional_tsquery = " | ".join(f"({p})" for p in optional_parts) if optional_parts else None

    # Защита (владелец, 28.10.2026, QA-находка): apply_numeric=False СНИМАЕТ
    # цифровой фильтр — если при этом required-текста тоже нет (required
    # был ТОЛЬКО из цифровых токенов, "зюзюкремлик 4125" → required=["4125"]
    # после parse_query), WHERE остаётся ПУСТЫМ и запрос вернул бы ВСЮ
    # таблицу. Такую комбинацию (ослаблять единственное условие) запрещаем
    # прямо здесь — не только на уровне вызывающего search_products.
    if not apply_numeric and not required_tsquery and numeric_tokens:
        return [], 0

    bare_numbers = [n for n in (_bare_number(t) for t in numeric_tokens) if n] if not apply_numeric else []

    def _base(entity):
        q = select(entity)
        q = _apply_non_search_filters(q, filters, freshness_ctx)
        if required_tsquery:
            q = q.where(
                text(f"{_FTS_DOC_SQL} @@ to_tsquery('russian', :req_tsquery_w)")
                .bindparams(req_tsquery_w=required_tsquery)
            )
        if apply_numeric:
            for tok in numeric_tokens:
                q = q.where(_numeric_condition(tok))
        return q

    count_q = select(func.count()).select_from(_base(Product.id).subquery())
    total = (await db.execute(count_q)).scalar_one()

    order_terms = []
    if bare_numbers:
        # «похоже» бонус: голое число где-то в тексте (без строгой границы
        # единицы/формата) — считается ПЕРВЫМ (важнее ts_rank), чтобы
        # «ближе по величине» реально поднимало строку выше.
        bonus_pattern = "|".join(rf"(?<!\d){re.escape(n)}(?!\d)" for n in bare_numbers)
        order_terms.append(
            text(
                f"(CASE WHEN {_FTS_DOC_SQL}::text ~* :bare_num_pattern THEN 1 ELSE 0 END) DESC"
            ).bindparams(bare_num_pattern=bonus_pattern)
        )
    if required_tsquery or optional_tsquery:
        rank_sql = f"ts_rank({_FTS_DOC_SQL}, to_tsquery('russian', :req_tsquery_r))" if required_tsquery else "0"
        rank_params = {"req_tsquery_r": required_tsquery} if required_tsquery else {}
        if optional_tsquery:
            rank_sql += f" + COALESCE(ts_rank({_FTS_DOC_SQL}, to_tsquery('russian', :opt_tsquery_r)), 0)"
            rank_params["opt_tsquery_r"] = optional_tsquery
        order_terms.append(text(f"{rank_sql} DESC").bindparams(**rank_params))

    page_q = _base(Product).options(defer(Product.characteristics))
    page_q = page_q.order_by(*order_terms, Product.name.asc(), Product.id.asc())
    page_q = page_q.limit(limit).offset(offset)
    items = (await db.execute(page_q)).scalars().all()
    return list(items), total


async def _fetch_fts_page_or(
    db: AsyncSession,
    filters: ProductSearchFilters,
    words: list,
    *,
    limit: int,
    offset: int,
    freshness_ctx: Optional[FreshnessContext],
) -> tuple[list[Product], int]:
    """Шаг 3 лестницы (владелец, 28.10.2026): слова, которые были
    «повышены» из optional в required (ничего специфичного parse_query не
    нашло — полностью нераспознанная фраза), ослабляются с AND до OR — та
    же OR-группа, что у optional-ранжирования, но теперь как САМ фильтр
    (WHERE), не только бонус ранга. Используется ТОЛЬКО когда исходных
    required (бренд/вид/цифра/величина) не было вовсе — см. search_products."""
    parts = [p for p in (_tsquery_token(w, prefix=False) for w in words) if p]
    or_tsquery = " | ".join(f"({p})" for p in parts) if parts else None
    if not or_tsquery:
        return [], 0

    def _base(entity):
        q = select(entity)
        q = _apply_non_search_filters(q, filters, freshness_ctx)
        q = q.where(
            text(f"{_FTS_DOC_SQL} @@ to_tsquery('russian', :or_tsquery_w)")
            .bindparams(or_tsquery_w=or_tsquery)
        )
        return q

    count_q = select(func.count()).select_from(_base(Product.id).subquery())
    total = (await db.execute(count_q)).scalar_one()

    rank_expr = text(
        f"ts_rank({_FTS_DOC_SQL}, to_tsquery('russian', :or_tsquery_r)) DESC"
    ).bindparams(or_tsquery_r=or_tsquery)
    page_q = _base(Product).options(defer(Product.characteristics))
    page_q = page_q.order_by(rank_expr, Product.name.asc(), Product.id.asc())
    page_q = page_q.limit(limit).offset(offset)
    items = (await db.execute(page_q)).scalars().all()
    return list(items), total


async def _search_legacy_page(
    db: AsyncSession,
    filters: ProductSearchFilters,
    *,
    limit: int,
    offset: int,
    freshness_ctx: Optional[FreshnessContext],
) -> tuple[list[Product], int, bool]:
    """Старый containment-путь (AND ILIKE по словам + гибридное
    startswith-ранжирование широких запросов) — теперь используется для:
    1) запросов-артикулов/кодов (_looks_like_article_query); 2) слов короче
    MIN_TRIGRAM_WORD_LEN; 3) ЗАПАСНЫМ путём, если полнотекстовый поиск
    (_fetch_fts_page) дал 0 строк, перед fuzzy (владелец, 28.10.2026,
    ревью «этап 0»)."""
    total, total_capped = await count_products(db, filters, freshness_ctx)
    if total > RANK_FULL_THRESHOLD and offset + limit <= HYBRID_OFFSET_LIMIT_CAP:
        items = await _fetch_hybrid_page(db, filters, freshness_ctx, limit=limit, offset=offset)
    else:
        q = build_product_search_query(filters=filters, freshness_ctx=freshness_ctx)
        q = q.limit(limit).offset(offset)
        items = (await db.execute(q)).scalars().all()
    return list(items), total, total_capped


async def search_products(
    db: AsyncSession,
    filters: ProductSearchFilters,
    *,
    limit: int,
    offset: int,
    freshness_ctx: Optional[FreshnessContext] = None,
    result_meta: Optional[dict] = None,
) -> tuple[list[Product], int, bool]:
    """Возвращает (товары страницы, total по тем же фильтрам, total_capped).

    При search (владелец, 28.10.2026, ревью «этап 0», ДОРАБОТКА того же
    дня — старый «фаззи по всей строке» матчил посторонние товары,
    «огнетушитель порошковый 4 кг» находил кабели) — артикул/код/слишком
    короткие слова — как раньше (_search_legacy_page, без исправления
    опечаток — коды не словарные слова). Иначе — ЛЕСТНИЦА (первый шаг,
    давший total>0, побеждает):
      1. Точное: FTS required (AND, последнее слово — с :*) + цифровые/
         величина-токены — СТРОГИЙ пост-фильтр по регулярке (граница числа).
         (1.5 — старый containment-путь как ещё одна «точная» попытка, см.
         комментарий у вызова _search_legacy_page ниже.)
      2. Если (1)=0 и были цифровые/величина-токены (и есть required-текст,
         на котором держится фильтр) — те же required, но БЕЗ строгого
         цифрового фильтра (apply_numeric=False) — только мягкий бонус
         ранга, если голое число где-то есть. result_meta["relaxed"] —
         список ослабленных токенов.
      3. Если (2)=0 (или пропущен) — ИСПРАВЛЕНИЕ ОПЕЧАТОК ПО СЛОВАМ
         (product_words_correction.correct_unknown_words): каждое
         неизвестное слово required заменяется на ближайшее слово словаря
         каталога (MV product_words, similarity >= 0.5), лестница 1-2
         повторяется с исправленными словами. result_meta["fuzzy"]=True,
         result_meta["corrected"]={исходное: исправленное}. ПЕРЕД шагом 4
         (не после) — живая проверка на стенде показала: OR по
         нераспознанным словам раньше находил посторонние товары по
         совпавшему-но-не-опечатанному слову, пока опечатка в ДРУГОМ слове
         не исправлена.
      4. Если (3)=0 и required был «повышен» из optional (т.е. parse_query
         ничего специфичного не нашёл — полностью нераспознанная фраза) —
         AND ослабляется до OR (_fetch_fts_page_or): товар должен содержать
         ХОТЯ БЫ ОДНО из слов, не все. Самый нестрогий шаг, последний.
      Ничего не нашлось — total=0, без похода в trgm по всей строке (тот
      механизм убран, Правило №6 — один механизм опечаток).

    result_meta — опциональный dict ДЛЯ ЧТЕНИЯ ВЫЗЫВАЮЩЕЙ СТОРОНОЙ
    (products_page.py): query_specific/fuzzy/relaxed/corrected — сигнатура/
    контракт самого search_products НЕ меняется (3-tuple, как раньше)."""
    if result_meta is not None:
        result_meta.setdefault("query_specific", False)
        result_meta.setdefault("fuzzy", False)
        result_meta.setdefault("relaxed", [])
        result_meta.setdefault("corrected", {})

    if not filters.search:
        q = build_product_search_query(filters=filters, freshness_ctx=freshness_ctx)
        q = q.limit(limit).offset(offset)
        items = (await db.execute(q)).scalars().all()
        total, total_capped = await count_products(db, filters, freshness_ctx)
        return list(items), total, total_capped

    raw = filters.search

    # Ни буквы, ни цифры во всей строке ("%%%", "...", одни пробелы/
    # спецсимволы) — осмысленного условия построить не из чего, пустой
    # результат БЕЗ похода в БД (владелец, 28.10.2026, QA-находка (б)).
    if not _has_letter_or_digit(raw):
        return [], 0, False

    if _all_words_too_short_for_trigram(raw) or _looks_like_article_query(raw):
        items, total, _total_capped = await _search_legacy_page(
            db, filters, limit=limit, offset=offset, freshness_ctx=freshness_ctx,
        )
        return list(items), total, False

    brand_dictionary = await get_manufacturer_brand_dictionary(db)
    parsed = parse_query(raw, brand_dictionary=brand_dictionary)
    if result_meta is not None:
        result_meta["query_specific"] = parsed.specific

    required, optional = parsed.required, parsed.optional
    promoted = not required
    if promoted:
        # Ничего специфичного (бренд/цифра/величина/распознанный вид
        # товара) — «повышаем» ВСЕ значимые слова до required (AND), иначе
        # полностью нераспознанная фраза искалась бы без единого
        # обязательного условия (расхождение со старым строгим AND).
        required, optional = optional, []
    if not _required_has_usable_token(required):
        # Required целиком — мусор после очистки (операторы/спецсимволы,
        # "a:b & | !(" — буквы в исходной строке есть, но ни один токен не
        # даёт ни цифры, ни непустого текста) — FTS-запрос БЕЗ единого
        # реального условия строить нельзя, прямиком на легаси (владелец,
        # 28.10.2026, QA-находка (б)).
        items, total, _ = await _search_legacy_page(
            db, filters, limit=limit, offset=offset, freshness_ctx=freshness_ctx,
        )
        return list(items), total, False

    text_tokens, numeric_tokens = _split_required_tokens(required)

    def _mk_parsed(req_text: list, req_numeric: list, opt: list) -> ParsedQuery:
        return ParsedQuery(
            raw=parsed.raw, required=[*req_text, *req_numeric], optional=opt,
            dropped_stopwords=parsed.dropped_stopwords, specific=parsed.specific,
            brand=parsed.brand, product_type=parsed.product_type,
        )

    # Шаг 1 — точное.
    fts_parsed = _mk_parsed(text_tokens, numeric_tokens, optional)
    items, total = await _fetch_fts_page(
        db, filters, fts_parsed, limit=limit, offset=offset, freshness_ctx=freshness_ctx,
        apply_numeric=True,
    )
    if total > 0:
        return list(items), total, False

    # Шаг 1.5 — старый containment-путь (AND ILIKE) КАК ЕЩЁ ОДНА «точная»
    # попытка (не ослабление): to_tsquery() для многосложных hyphen-слов
    # строит фразовый запрос по ЧАСТЯМ compound-лексемы (Postgres hword-
    # разбор) и может не совпасть с документом, где то же слово — часть
    # БОЛЕЕ ДЛИННОГО составного токена (напр. запрос «стейл-тест» против
    # названия «Старый-стейл-тест» — 3-словный compound, а не 2-словный,
    # разные позиции лексем) — ILIKE по подстроке таких границ не знает и
    # находит. Если и тут 0 — переходим к ОСЛАБЛЕНИЮ (шаги 2-4).
    items, total, _ = await _search_legacy_page(
        db, filters, limit=limit, offset=offset, freshness_ctx=freshness_ctx,
    )
    if total > 0:
        return list(items), total, False

    # Шаг 2 — ослабить цифры/величины (владелец, 28.10.2026, доработка).
    # ТОЛЬКО если есть required-ТЕКСТ, на котором держится фильтр — иначе
    # (required был чисто цифровым, "зюзюкремлик 4125"→required=["4125"])
    # снятие единственного условия отдало бы всю таблицу (см. защиту внутри
    # _fetch_fts_page, здесь — чтобы не тратить лишний запрос в БД).
    if numeric_tokens and text_tokens:
        items, total = await _fetch_fts_page(
            db, filters, fts_parsed, limit=limit, offset=offset, freshness_ctx=freshness_ctx,
            apply_numeric=False,
        )
        if total > 0:
            if result_meta is not None:
                result_meta["relaxed"] = list(numeric_tokens)
            return list(items), total, False

    # Шаг 3 — исправление опечаток ПО СЛОВАМ (словарь product_words,
    # Правило №6 — единственный механизм опечаток, старый trgm-по-всей-
    # строке убран). ПЕРЕД ослаблением AND→OR (владелец, 28.10.2026,
    # доработка после живой проверки на стенде: «огнитушитель порошковый»
    # — оба слова нераспознанные/опечатка — OR находил ПОСТОРОННИЕ товары
    # по слову «порошковый» (проволока порошковая, модуль порошкового
    # пожаротушения) РАНЬШЕ, чем срабатывала точная коррекция «огнитушитель»
    # → «огнетушитель»; сначала чиним слово, потом — если всё равно 0 —
    # ослабляем AND до OR).
    correction_words: list = []
    for tok in text_tokens:
        correction_words.extend(_tsquery_word(tok).split())
    corrections = await correct_unknown_words(db, correction_words)
    if corrections:
        corrected_text_tokens = [
            " ".join(corrections.get(w, w) for w in _tsquery_word(tok).split()) or tok
            for tok in text_tokens
        ]
        corrected_parsed = _mk_parsed(corrected_text_tokens, numeric_tokens, optional)
        items, total = await _fetch_fts_page(
            db, filters, corrected_parsed, limit=limit, offset=offset, freshness_ctx=freshness_ctx,
            apply_numeric=True,
        )
        relaxed: list = []
        if total == 0 and numeric_tokens and text_tokens:
            items, total = await _fetch_fts_page(
                db, filters, corrected_parsed, limit=limit, offset=offset, freshness_ctx=freshness_ctx,
                apply_numeric=False,
            )
            relaxed = list(numeric_tokens)
        if total > 0:
            if result_meta is not None:
                result_meta["fuzzy"] = True
                result_meta["corrected"] = corrections
                result_meta["relaxed"] = relaxed
            return list(items), total, False

    # Шаг 4 — ослабить AND до OR, но ТОЛЬКО если required был «повышен» из
    # optional (нераспознанная фраза) — распознанный вид товара/бренд
    # ослаблять до «любое слово из фразы» не нужно (это сломало бы точность
    # для реально специфичных запросов). Последний шаг — самый нестрогий.
    if promoted and text_tokens:
        items, total = await _fetch_fts_page_or(
            db, filters, text_tokens, limit=limit, offset=offset, freshness_ctx=freshness_ctx,
        )
        if total > 0:
            if result_meta is not None:
                result_meta["relaxed"] = list(text_tokens)
            return list(items), total, False

    return [], 0, False
