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
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from sqlalchemy import Select, and_, case, func, literal, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.models.product import Product
from app.services.price_freshness import FreshnessContext
from app.services.price_freshness_sql import apply_stale_join

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


async def search_products(
    db: AsyncSession,
    filters: ProductSearchFilters,
    *,
    limit: int,
    offset: int,
    freshness_ctx: Optional[FreshnessContext] = None,
) -> tuple[list[Product], int, bool]:
    """Возвращает (товары страницы, total по тем же фильтрам, total_capped).
    total — ОТДЕЛЬНЫЙ count-запрос по тем же условиям (не COUNT(*) OVER() —
    страница рассчитана на limit<=200, второй лёгкий запрос дешевле, чем
    тащить window-функцию по каждой строке первого); count_products() всегда
    точный, без потолка (см. докстринг там). При search —
    total считается ПЕРВЫМ и его же значение решает, идти ли гибридным
    путём (total > RANK_FULL_THRESHOLD) — второго count-запроса на принятие
    решения не нужно (Правило №6)."""
    if filters.search:
        total, total_capped = await count_products(db, filters, freshness_ctx)
        if total > RANK_FULL_THRESHOLD and offset + limit <= HYBRID_OFFSET_LIMIT_CAP:
            items = await _fetch_hybrid_page(db, filters, freshness_ctx, limit=limit, offset=offset)
        else:
            q = build_product_search_query(filters=filters, freshness_ctx=freshness_ctx)
            q = q.limit(limit).offset(offset)
            items = (await db.execute(q)).scalars().all()
        return list(items), total, total_capped

    q = build_product_search_query(filters=filters, freshness_ctx=freshness_ctx)
    q = q.limit(limit).offset(offset)
    items = (await db.execute(q)).scalars().all()
    total, total_capped = await count_products(db, filters, freshness_ctx)
    return list(items), total, total_capped
