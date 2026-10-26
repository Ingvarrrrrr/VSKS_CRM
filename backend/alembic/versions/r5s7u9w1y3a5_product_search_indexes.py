"""Индексы каталога товаров под серверный поиск/фильтры (ПРАВИЛО №8 п.11,
владелец, 2026-10-26).

Повод: каталог products на проде — 53 797 строк, вырастет до 250+ тыс.
GET /api/products/ без limit отдавал ВЕСЬ каталог. Это шаг 1 (бэкенд-ядро) —
индексы под новый сервис app/services/product_search.py:
  - pg_trgm (CREATE EXTENSION) — нужен для GIN gin_trgm_ops и для
    similarity() в ранжировании поиска;
  - GIN trigram по name, article И manufacturer — ILIKE '%слово%' по этим
    трём колонкам (app/services/product_search.py::_word_condition) без
    индекса на manufacturer планировщик на 263 тыс. строк (замер владельца,
    2026-10-26) выбирал Seq Scan целиком (OR по трём условиям, индекс есть
    только у двух из трёх — пользы от частичного покрытия planner не видел);
    с индексом на все три — BitmapOr по всем трём индексам, 339мс → 212мс на
    частое слово «кабель» (24280 из 263360 строк, ILIKE поддерживается
    напрямую без lower()-обёртки);
  - description — СОЗНАТЕЛЬНО БЕЗ индекса (замер на локальной копии,
    26336 строк, ~45% с описанием: GIN trgm по description = 13 MB при
    размере таблицы 115 MB — на прод-объёме это уйдёт за ~25-30 MB ради
    поля, которое не является основным критерием поиска и которое почти
    всегда ищут вместе с именем/артикулом. Поиск по описанию — только по
    явному флагу search_description, через ILIKE без индекса (см.
    app/services/product_search.py));
  - функциональный B-tree индекс под normalize_product_name(name) —
    выражение ТЕКСТУАЛЬНО совпадает с app/services/product_catalog_match.py
    ::_sql_normalized_name_expr() (Правило №6 — тот же _CHAR_FOLD_MAP,
    импортирован отсюда, а не продублирован строкой);
  - B-tree по category, product_type, is_active, feo_category_id — фильтры
    страницы «Товары»;
  - B-tree (name, id) и (price, id) — ПАГИНАЦИЯ/СОРТИРОВКА без поиска
    (ORDER BY name/price + id-тайбрейк, offset=N) — владелец, 26.10.2026,
    второй замер на 263 тыс. товаров (после первого прохода этой миграции):
    без этих индексов ORDER BY name LIMIT 50 OFFSET 5000 шёл Parallel Seq
    Scan + external merge sort на диск — 3.7с; с индексом (name, id) —
    Index Scan сразу забирает нужный диапазон — 14мс. ORDER BY price DESC —
    аналогично (0.5мс с индексом). GiST-индекс по name (gist_trgm_ops) для
    KNN-сортировки ПРОВЕРЕН и ОТКЛОНЁН — на запросе из двух слов планировщик
    иногда выбирал его вместо GIN для ILIKE-фильтра и становился МЕДЛЕННЕЕ
    (74мс против 4мс с одним GIN) — GIN уже покрывает оба случая
    использования (containment-поиск и BitmapOr), второй индекс по тому же
    выражению не нужен (Правило №6 — один механизм для одной задачи).
  - функциональный B-tree ix_products_name_lower_id (lower(name), id) —
    ГИБРИДНОЕ ранжирование широких запросов (владелец, 26.10.2026,
    доработка после первого прохода: "кабель" 24 тыс. совпадений — 690мс,
    "кб" — 330мс даже при малом числе совпадений, см. docstring
    app/services/product_search.py::_fetch_hybrid_page). ВАЖНО: operator
    class — DEFAULT (НЕ text_pattern_ops, его тут специально НЕТ): group A
    ("имя начинается с запроса") ищется через ПРОСТОЕ range-условие
    (lower(name) >= lo AND lower(name) < hi), не через LIKE 'prefix%'.
    Пробовали text_pattern_ops с LIKE — планировщик путает оценку
    кардинальности composite-условия (range+LIKE) и уходит в полный скан
    по другому индексу (650-890мс); чистый range по default-коллации
    (en_US.utf8 — не C!) планировщик оценивает верно и сразу делает
    Index Scan без отдельного Sort (<1мс) — см. _startswith_condition()
    и её докстринг, почему именно так и чем это рискует (collation-грань
    на экзотических кодпойнтах, не встречается в реальных запросах).
  - функциональный B-tree индекс ix_products_dedup_normalized_name —
    выражение ТЕКСТУАЛЬНО совпадает с app/services/product_dedup_sql.py
    ::dedup_normalized_name_sql_text() (Правило №6, та же формула, что и
    GROUP BY в POST /api/products/deduplicate — без индекса это seq scan по
    всему каталогу на каждый вызов). GROUP BY по выражению над ВСЕЙ таблицей
    у Postgres обычно всё равно планируется как seq scan + сортировка/
    хэш-агрегация (индекс по равенству здесь не исключает чтение всех строк
    таблицы) — индекс даёт Index Only Scan тем запросам, где к выражению
    добавляется локальный предикат (например, WHERE <expr> = <ключ> при
    повторной проверке конкретной группы), и ускоряет саму GROUP BY за счёт
    готового отсортированного по ключу набора (убирает сортировку перед
    хэш/групп-агрегацией на больших объёмах) — см. замер в отчёте сессии.

Индексы создаются CONCURRENTLY (autocommit_block) — не блокируют запись в
products во время построения на проде (53 797 строк).
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "r5s7u9w1y3a5"
down_revision = "p9o8i7u6y5t4"
branch_labels = None
depends_on = None


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _normalized_name_expr() -> str:
    """Та же формула, что app/services/product_catalog_match.py
    ::_sql_normalized_name_expr() — translate() строится из ОДНОГО
    _CHAR_FOLD_MAP (Правило №6, не второй литерал с теми же символами)."""
    from app.services.product_catalog_match import _SQL_FROM_CHARS, _SQL_TO_CHARS

    return (
        "lower(regexp_replace(trim(translate(name, "
        f"{_sql_quote(_SQL_FROM_CHARS)}, {_sql_quote(_SQL_TO_CHARS)})), "
        "'\\s+', ' ', 'g'))"
    )


def _dedup_normalized_name_expr() -> str:
    """Текст индекса под GROUP BY дедупа (POST /api/products/deduplicate) —
    выражение берётся из app/services/product_dedup_sql.py
    ::dedup_normalized_name_sql_text() (Правило №6, единый источник с
    sql_dedup_normalized_name_expr(), которым строится сам запрос), а не
    переписывается здесь строкой."""
    from app.services.product_dedup_sql import dedup_normalized_name_sql_text

    return dedup_normalized_name_sql_text("name")


def upgrade() -> None:
    # Расширение — в обычной (не autocommit) транзакции, как и остальной DDL
    # этой миграции без CONCURRENTLY.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    norm_expr = _normalized_name_expr()

    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_name_trgm "
            "ON products USING gin (name gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_article_trgm "
            "ON products USING gin (article gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_manufacturer_trgm "
            "ON products USING gin (manufacturer gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_name_normalized "
            f"ON products ({norm_expr})"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_category "
            "ON products (category)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_product_type "
            "ON products (product_type)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_is_active "
            "ON products (is_active)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_feo_category_id "
            "ON products (feo_category_id)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_dedup_normalized_name "
            f"ON products ({_dedup_normalized_name_expr()})"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_name_id "
            "ON products (name, id)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_price_id "
            "ON products (price, id)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_name_lower_id "
            "ON products (lower(name), id)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_name_lower_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_price_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_name_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_dedup_normalized_name")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_feo_category_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_is_active")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_product_type")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_category")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_name_normalized")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_manufacturer_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_article_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_name_trgm")
    # Расширение НЕ удаляем — может использоваться другими объектами.
