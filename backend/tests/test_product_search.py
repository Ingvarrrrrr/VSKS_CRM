# -*- coding: utf-8 -*-
"""Серверный поиск/фильтры/пагинация каталога товаров (владелец, 26.10.2026,
план: каталог 53 797 товаров на проде, растёт к 250+ тыс. — GET
/api/products/ без limit отдавал ВЕСЬ каталог).

Покрывает:
  - app/services/product_search.py — многословный поиск (AND), ранжирование,
    фильтры, пагинация (total/offset);
  - app/services/price_freshness_sql.py::stale_condition — SQL-формула ==
    price_freshness.evaluate()['is_stale'] на разношёрстном наборе товаров
    (разные TTL-правила, курсовой сдвиг, без цены/даты) — ПРАВИЛО №6, один
    источник правды для "требует актуализации" и в Python, и в SQL;
  - GET /api/products/page (limit>200 → 422, sort вне белого списка → 422);
  - GET /api/products/ (ids>500 → 422, limit>200 обрезается до 200, не 422 —
    обратная совместимость со старыми вызывающими).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.fx_rate import FxRate
from app.models.price_freshness_rule import PriceFreshnessRule
from app.models.product import Product
from app.schemas.products import ProductOut
from app.services.price_freshness import evaluate as evaluate_freshness, load_context as load_freshness_context
from app.services.price_freshness_sql import apply_stale_join
from app.services.product_search import (
    MAX_IDS,
    MAX_LIMIT,
    ProductSearchFilters,
    build_product_search_query,
    count_stale_products,
    search_products,
)
import app.services.product_search as product_search_module
from app.services.product_search import _prefix_upper_bound, _startswith_condition

TODAY = datetime.utcnow().date()


def _mk(db_session, **kwargs):
    p = Product(name=kwargs.pop("name"), category=kwargs.pop("category", "Прочее"), **kwargs)
    db_session.add(p)
    return p


# ── Многословный поиск (AND) и ранжирование ─────────────────────────────────

@pytest.mark.asyncio
async def test_multi_word_search_requires_all_words(db_session):
    """build_product_search_query() НАПРЯМУЮ — старый строгий AND-механизм
    (не search_products()): он остаётся в коде и используется для
    артикулов/кодов и как запасной путь (см. _search_legacy_page), но
    search_products() для обычных словарных фраз теперь идёт через
    полнотекстовый поиск — там же "медный" уже НЕ обязателен, см. раздел
    «Этап 0» ниже (владелец, 28.10.2026, ревью «этап 0»)."""
    a = _mk(db_session, name="Кабель медный ВВГ 3х2.5")
    b = _mk(db_session, name="Кабель алюминиевый АВВГ")
    c = _mk(db_session, name="Труба медная")
    await db_session.commit()

    filters = ProductSearchFilters(search="кабель медный")
    q = build_product_search_query(filters=filters)
    rows = (await db_session.execute(q)).scalars().all()
    ids = {p.id for p in rows}
    assert a.id in ids
    assert b.id not in ids
    assert c.id not in ids


# ── «Этап 0» (владелец, 28.10.2026): полнотекстовый поиск PostgreSQL
#    (to_tsvector('russian', ...)) + pg_trgm для опечаток — ТЕПЕРЬ для
#    ЛЮБОГО обычного (не артикул/код) запроса через search_products(),
#    не только когда parse_query() находит специфичный признак ─────────────

@pytest.mark.asyncio
async def test_general_query_extra_words_do_not_block_match(db_session):
    """"носилки металлические складные" (лишние слова/предлог) — через
    search_products() теперь находит товар без слова "металлические"
    (required — только "носилки", распознанное как вид товара;
    "металлические"/"складные" — ranking-бонус, не AND). "носилки" (не
    "кабель") — на дев-стенде с реальным каталогом редкое слово (11 строк),
    "кабель" дал бы тысячи посторонних совпадений и не прошёл бы в top-50
    по ранжированию (см. уникальные префиксы в тестах гибрида выше)."""
    a = _mk(db_session, name="Носилки металлические складные ВВГ")
    also_matches = _mk(db_session, name="Носилки пластиковые")
    unrelated = _mk(db_session, name="Труба стальная оцинкованная")
    await db_session.commit()

    filters = ProductSearchFilters(search="носилки металлические складные")
    items, total, capped = await search_products(db_session, filters, limit=50, offset=0)
    ids = {p.id for p in items}
    assert a.id in ids
    assert also_matches.id in ids  # "носилки" совпал, "металлические" — не AND
    assert unrelated.id not in ids


@pytest.mark.asyncio
async def test_general_query_fully_unrecognized_phrase_still_requires_all_words(db_session):
    """Фраза без распознанных сигналов (ни вида товара, ни бренда, ни
    цифры/величины) — ВСЕ слова становятся required (AND), иначе часть
    фразы не участвовала бы вовсе (владелец, 28.10.2026)."""
    a = _mk(db_session, name="Фаззигенерик стальная плита толстая")
    b = _mk(db_session, name="Фаззигенерик алюминиевая плита")
    await db_session.commit()

    filters = ProductSearchFilters(search="фаззигенерик стальная плита")
    items, total, capped = await search_products(db_session, filters, limit=50, offset=0)
    ids = {p.id for p in items}
    assert a.id in ids
    assert b.id not in ids  # нет "стальная" — required не выполнен


@pytest.mark.asyncio
async def test_general_query_matches_declined_word_form(db_session):
    """Словоформа без всякой "специфики" (ни бренда, ни цифры) — стеммер
    PostgreSQL находит "огнетушителя" (родительный падеж) по запросу
    "огнетушитель" (именительный) и через ОБЫЧНЫЙ (не specific) путь
    search_products() (владелец, 28.10.2026, ревью «этап 0»)."""
    match = _mk(db_session, name="Фаззисклад для огнетушителя порошкового")
    unrelated = _mk(db_session, name="Фаззисклад для метел")
    await db_session.commit()

    filters = ProductSearchFilters(search="фаззисклад огнетушитель")
    items, total, capped = await search_products(db_session, filters, limit=50, offset=0)
    ids = {p.id for p in items}
    assert match.id in ids
    assert unrelated.id not in ids


@pytest.mark.asyncio
async def test_brand_from_own_manufacturer_makes_query_specific_without_digit(db_session):
    """Бренд из своего manufacturer (get_manufacturer_brand_dictionary,
    кэш) делает запрос specific=True ДАЖЕ без цифры — "болгарка макита"
    (владелец, 28.10.2026, п.3 ревью «этап 0»). Кэш сбрасывается явно —
    он модульный (процесс-wide) и мог прогреться другим тестом ДО вставки
    этого manufacturer."""
    import app.services.product_query_parse as product_query_parse_module
    product_query_parse_module._brand_dict_cache["dictionary"] = None
    product_query_parse_module._brand_dict_cache["built_at"] = 0.0

    match = _mk(db_session, name="Фаззиброндтест Макита углошлифовальная", manufacturer="Макита")
    other_brand = _mk(db_session, name="Фаззиброндтест Bosch углошлифовальная", manufacturer="Bosch")
    await db_session.commit()

    filters = ProductSearchFilters(search="фаззиброндтест макита")
    meta: dict = {}
    items, total, capped = await search_products(
        db_session, filters, limit=50, offset=0, result_meta=meta,
    )
    ids = {p.id for p in items}
    assert meta["query_specific"] is True
    assert match.id in ids
    assert other_brand.id not in ids

@pytest.mark.asyncio
async def test_specific_query_extra_words_and_declined_word_form(db_session):
    """«Лишние слова» ("порошковый", "для" — опционально/отброшено) не
    мешают найти товар, а словоформа ("огнетушителя", родительный падеж в
    самом названии) находится по запросу в именительном ("огнетушитель") —
    это делает стеммер PostgreSQL ('russian'), а не наша ручная обрезка
    окончаний (задание владельца: обрезку окончаний вручную не писать)."""
    match = _mk(db_session, name="Шкаф для огнетушителя порошкового 4 кг")
    unrelated = _mk(db_session, name="Труба стальная оцинкованная")
    await db_session.commit()

    filters = ProductSearchFilters(search="огнетушитель порошковый 4 кг")
    items, total, capped = await search_products(db_session, filters, limit=50, offset=0)
    ids = {p.id for p in items}
    assert match.id in ids
    assert unrelated.id not in ids
    assert capped is False


@pytest.mark.asyncio
async def test_specific_query_type_word_excludes_other_type(db_session):
    """«Болгарка» не находит огнетушитель — required-токен вида товара
    ("болгарка") идёт в tsquery через AND, не через OR с остальными
    словами (владелец, 28.10.2026)."""
    bolgarka = _mk(db_session, name="Болгарка Makita 125")
    fire_extinguisher = _mk(db_session, name="Огнетушитель порошковый 125")
    await db_session.commit()

    filters = ProductSearchFilters(search="болгарка 125")
    items, total, capped = await search_products(db_session, filters, limit=50, offset=0)
    ids = {p.id for p in items}
    assert bolgarka.id in ids
    assert fire_extinguisher.id not in ids


@pytest.mark.asyncio
async def test_specific_query_numeric_boundary_125_not_1250(db_session):
    """Цифровой required-токен «125» ищется по границе числа (~* с
    lookaround) — не находит «1250» (владелец, 28.10.2026, задание "этап
    0": "цифры/величины ... пост-фильтр по границе числа")."""
    exact = _mk(db_session, name="Болгарка Makita 125")
    longer = _mk(db_session, name="Болгарка Makita 1250")
    await db_session.commit()

    filters = ProductSearchFilters(search="болгарка 125")
    items, total, capped = await search_products(db_session, filters, limit=50, offset=0)
    ids = {p.id for p in items}
    assert exact.id in ids
    assert longer.id not in ids


@pytest.mark.asyncio
async def test_specific_query_relaxes_quantity_when_exact_not_found(db_session):
    """Шаг 2 лестницы (владелец, 28.10.2026, доработка «этап 0» — QA-находка
    про огнетушители/кабели: «огнетушитель порошковый 4 кг» должен находить
    «Огнетушитель порошковый ОП-2» через ослабление, не через посторонние
    товары). «носилки» — редкое слово словаря вида товара (PRODUCT_TYPE_
    WORDS), required-ТЕКСТ остаётся обязательным — именно поэтому товар
    ДРУГОГО вида, у которого ЕСТЬ точное «4 кг», НЕ находится (required-
    текст не совпал), а товар «носилки» без точного «4 кг» — находится,
    через relaxed."""
    close = _mk(db_session, name="Носилки металлические складные")  # нет "4 кг"
    other_type = _mk(db_session, name="Тачка строительная 4 кг")  # "4 кг" есть, но не "носилки"
    await db_session.commit()

    filters = ProductSearchFilters(search="носилки металлические 4 кг")
    meta: dict = {}
    items, total, capped = await search_products(
        db_session, filters, limit=50, offset=0, result_meta=meta,
    )
    ids = {p.id for p in items}
    assert close.id in ids
    assert other_type.id not in ids
    assert meta["relaxed"] == ["4 кг"]
    assert meta["fuzzy"] is False
    assert meta["corrected"] == {}


@pytest.mark.asyncio
async def test_specific_query_truly_zero_results_fuzzy_stays_empty(db_session):
    """specific=True (цифровой токен), вся лестница (точно → ослабить
    цифры → ослабить до OR → исправление опечаток по словарю product_words)
    не находит ничего для заведомо выдуманного слова/числа — честный
    total=0, fuzzy=False, не падает (владелец, 28.10.2026, доработка «этап
    0»). Слово "зюзюкремлик" — специально придуманное, ни в одном реальном
    слове словаря каталога нет похожего (similarity < 0.5, проверено
    вручную psql)."""
    filters = ProductSearchFilters(search="зюзюкремлик 4125")
    meta: dict = {}
    items, total, capped = await search_products(
        db_session, filters, limit=50, offset=0, result_meta=meta,
    )
    assert meta["query_specific"] is True
    assert total == 0
    assert meta["fuzzy"] is False
    assert meta["corrected"] == {}
    assert items == []


@pytest.mark.asyncio
async def test_typo_query_corrected_via_product_words_dictionary(db_session):
    """Опечатка в обычном (не specific) запросе — шаг 4 лестницы:
    "огнИтушитель" не найден ни одним из шагов 1-3 (другой стем/другая
    подстрока), product_words_correction находит "огнетушитель"
    (similarity 0.625, см. отчёт сессии) в словаре каталога и переигрывает
    FTS с исправленным словом — находит РЕАЛЬНЫЕ товары каталога без
    создания тестовых (владелец, 28.10.2026, доработка «этап 0»: убран
    старый trgm-fallback по ВСЕЙ строке, который матчил посторонние
    товары — теперь исправление ТОЧЕЧНОЕ, по словам)."""
    filters = ProductSearchFilters(search="огнИтушитель")  # опечатка: И вместо Е
    meta: dict = {}
    items, total, capped = await search_products(
        db_session, filters, limit=50, offset=0, result_meta=meta,
    )
    assert meta["query_specific"] is False
    assert meta["fuzzy"] is True
    assert meta["corrected"] == {"огнитушитель": "огнетушитель"}
    assert total > 0
    assert all("огнетушит" in (p.name or "").lower() for p in items)


@pytest.mark.asyncio
async def test_search_ranks_exact_then_startswith_then_similarity(db_session):
    exact = _mk(db_session, name="Автомат")
    startswith = _mk(db_session, name="Автомат защитный ВА-47")
    fuzzy = _mk(db_session, name="Выключатель-автомат С16")
    await db_session.commit()

    filters = ProductSearchFilters(search="Автомат")
    q = build_product_search_query(filters=filters)
    rows = (await db_session.execute(q)).scalars().all()
    ids_in_order = [p.id for p in rows if p.id in {exact.id, startswith.id, fuzzy.id}]
    assert ids_in_order == [exact.id, startswith.id, fuzzy.id]


@pytest.mark.asyncio
async def test_short_word_search_uses_startswith_not_contains(db_session):
    """Все слова запроса короче 3 символов — pg_trgm их не индексирует,
    поэтому ищем только по префиксу имени (startswith), а не containment
    (см. MIN_TRIGRAM_WORD_LEN / _all_words_too_short_for_trigram)."""
    starts = _mk(db_session, name="КБ-1 автомат")
    middle = _mk(db_session, name="Трубка кб защитная")
    unrelated = _mk(db_session, name="Кабель медный")
    await db_session.commit()

    filters = ProductSearchFilters(search="кб")
    q = build_product_search_query(filters=filters)
    rows = (await db_session.execute(q)).scalars().all()
    ids = {p.id for p in rows}
    assert starts.id in ids
    assert middle.id not in ids
    assert unrelated.id not in ids


@pytest.mark.asyncio
async def test_like_wildcards_are_escaped(db_session):
    """Слово поиска с % _ \\ не должно вести себя как метасимвол LIKE."""
    normal = _mk(db_session, name="Товар 100% шерсть")
    other = _mk(db_session, name="Товар качество отличное")
    await db_session.commit()

    filters = ProductSearchFilters(search="100%")
    q = build_product_search_query(filters=filters)
    rows = (await db_session.execute(q)).scalars().all()
    ids = {p.id for p in rows}
    assert normal.id in ids
    assert other.id not in ids


# ── Фильтры и пагинация ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filters_category_product_type_active_price(db_session):
    keep = _mk(db_session, name="Стул офисный", category="Мебель", product_type="Стул", is_active=True, price=Decimal("1500"))
    wrong_cat = _mk(db_session, name="Стол офисный", category="Другое", product_type="Стол", is_active=True, price=Decimal("1500"))
    inactive = _mk(db_session, name="Стул старый", category="Мебель", product_type="Стул", is_active=False, price=Decimal("1500"))
    too_cheap = _mk(db_session, name="Стул дешёвый", category="Мебель", product_type="Стул", is_active=True, price=Decimal("10"))
    await db_session.commit()

    filters = ProductSearchFilters(
        category=["Мебель"], product_type=["Стул"], is_active=True,
        price_min=Decimal("100"), price_max=Decimal("5000"),
    )
    q = build_product_search_query(filters=filters)
    rows = (await db_session.execute(q)).scalars().all()
    ids = {p.id for p in rows}
    assert keep.id in ids
    assert wrong_cat.id not in ids
    assert inactive.id not in ids
    assert too_cheap.id not in ids


@pytest.mark.asyncio
async def test_pagination_total_and_offset(db_session):
    names = [f"Пагинация-товар-{i:02d}" for i in range(5)]
    for n in names:
        _mk(db_session, name=n)
    await db_session.commit()

    filters = ProductSearchFilters(search="Пагинация-товар")
    items, total, capped = await search_products(db_session, filters, limit=2, offset=0)
    assert total == 5
    assert capped is False
    assert len(items) == 2
    items2, total2, capped2 = await search_products(db_session, filters, limit=2, offset=4)
    assert total2 == 5
    assert capped2 is False
    assert len(items2) == 1


# ── stale SQL == evaluate() ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_condition_matches_evaluate(db_session, test_org):
    # Изолируем историю курса: дев-БД может уже содержать реальные fx_rates —
    # очищаем их в рамках транзакции теста (откатится в teardown db_session),
    # иначе "последний известный курс" в ctx был бы не тем, что мы вставили
    # здесь, и ожидаемый результат разошёлся бы со случайными боевыми данными.
    from sqlalchemy import delete as _sa_delete
    await db_session.execute(_sa_delete(FxRate))

    # Правила: category "Бытовая" -> 60, product_type "Еда" -> 14.
    db_session.add(PriceFreshnessRule(org_id=None, scope_kind="category", scope_key="СтейлБытовая", ttl_days=60))
    db_session.add(PriceFreshnessRule(org_id=None, scope_kind="product_type", scope_key="СтейлЕда", ttl_days=14))
    # Курс USD: 90 месяц назад, 100 сегодня (+11.1%, триггерит fx >=10%).
    db_session.add(FxRate(code="USD", rate_date=TODAY - timedelta(days=40), value=Decimal("90")))
    db_session.add(FxRate(code="USD", rate_date=TODAY, value=Decimal("100")))
    await db_session.commit()

    def _mkp(**kw):
        p = Product(name=kw.pop("name"), category=kw.pop("category", "Прочее"), **kw)
        db_session.add(p)
        return p

    rows = [
        _mkp(name="Без цены"),  # price None
        _mkp(name="Цена без даты", price=Decimal("10")),  # price_updated_at None
        _mkp(name="Свежая, категория 60", category="СтейлБытовая", price=Decimal("10"),
             price_updated_at=datetime.utcnow() - timedelta(days=5)),
        _mkp(name="Просрочена, категория 60", category="СтейлБытовая", price=Decimal("10"),
             price_updated_at=datetime.utcnow() - timedelta(days=90)),
        _mkp(name="Просрочена, тип 14", category="Прочее", product_type="СтейлЕда", price=Decimal("10"),
             price_updated_at=datetime.utcnow() - timedelta(days=20)),
        _mkp(name="Свежая, тип 14", category="Прочее", product_type="СтейлЕда", price=Decimal("10"),
             price_updated_at=datetime.utcnow() - timedelta(days=5)),
        # Курсовой триггер: 50 дней назад (>= курс с 40 дней назад известен),
        # базовый срок 60 (категория), ещё не истёк, но fx-сжатие до 30 истекло.
        _mkp(name="Курсовой триггер", category="СтейлБытовая", price=Decimal("10"),
             price_updated_at=datetime.utcnow() - timedelta(days=50)),
        _mkp(name="Персональный override", category="СтейлБытовая", price_ttl_days=5, price=Decimal("10"),
             price_updated_at=datetime.utcnow() - timedelta(days=10)),
    ]
    await db_session.commit()
    for r in rows:
        await db_session.refresh(r)

    org_id = None
    ctx = await load_freshness_context(db_session, org_id)

    expected_stale_ids = {r.id for r in rows if evaluate_freshness(r, ctx)["is_stale"]}

    q, cond = apply_stale_join(select(Product.id).where(Product.id.in_([r.id for r in rows])), ctx)
    q = q.where(cond)
    sql_stale_ids = set((await db_session.execute(q)).scalars().all())

    assert sql_stale_ids == expected_stale_ids
    # Sanity: обе множества не пустые/не полные — тест реально что-то проверяет.
    assert 0 < len(expected_stale_ids) < len(rows)


@pytest.mark.asyncio
async def test_stale_only_filter_and_stale_total(db_session):
    fresh = _mk(db_session, name="Свежий-стейл-тест", price=Decimal("10"), price_updated_at=datetime.utcnow())
    stale = _mk(db_session, name="Старый-стейл-тест", price=Decimal("10"), price_updated_at=datetime.utcnow() - timedelta(days=400))
    await db_session.commit()

    ctx = await load_freshness_context(db_session, None)
    filters = ProductSearchFilters(search="стейл-тест", stale_only=True)
    items, total, capped = await search_products(db_session, filters, limit=50, offset=0, freshness_ctx=ctx)
    ids = {p.id for p in items}
    assert stale.id in ids
    assert fresh.id not in ids

    stale_total = await count_stale_products(db_session, ctx)
    assert stale_total >= 1


# ── Эндпоинты: валидация лимитов/сортировки ДО запроса в БД ────────────────

@pytest.mark.asyncio
async def test_page_endpoint_limit_over_max_is_422(client, auth_headers):
    resp = await client.get("/api/products/page", params={"limit": MAX_LIMIT + 1}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_page_endpoint_sort_outside_whitelist_is_422(client, auth_headers):
    resp = await client.get("/api/products/page", params={"sort": "price_links"}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_page_endpoint_happy_path_shape(client, auth_headers, db_session):
    _mk(db_session, name="Page-shape-товар")
    await db_session.commit()
    resp = await client.get("/api/products/page", params={"search": "Page-shape-товар"}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    # query_specific/fuzzy/relaxed/corrected — «этап 0» (владелец,
    # 28.10.2026, доработка), опциональные поля ответа, см.
    # ProductSearchPageOut.
    assert set(body.keys()) == {
        "items", "total", "total_capped", "query_specific", "fuzzy", "relaxed", "corrected",
    }
    assert body["total"] >= 1
    assert body["total_capped"] is False


@pytest.mark.asyncio
async def test_stale_count_endpoint_shape(client, auth_headers):
    """GET /api/products/stale-count — отдельный эндпоинт (владелец,
    26.10.2026): /page больше не считает stale_total на каждый вызов."""
    resp = await client.get("/api/products/stale-count", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"stale_total"}
    assert isinstance(body["stale_total"], int)


@pytest.mark.asyncio
async def test_list_endpoint_ids_over_max_is_422(client, auth_headers):
    ids_csv = ",".join(str(i) for i in range(1, MAX_IDS + 2))
    resp = await client.get("/api/products/", params={"ids": ids_csv}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_endpoint_limit_over_max_is_clamped_not_422(client, auth_headers, db_session):
    for i in range(3):
        _mk(db_session, name=f"Clamp-товар-{i}")
    await db_session.commit()
    resp = await client.get("/api/products/", params={"search": "Clamp-товар", "limit": 10000}, headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── Гибридное ранжирование широких запросов (владелец, 26.10.2026,
#    доработка) — RANK_FULL_THRESHOLD понижен monkeypatch'ем, чтобы на
#    маленьком тестовом наборе (несколько строк) включился ИМЕННО гибридный
#    путь, а не полное similarity-ранжирование. ──────────────────────────────

def test_prefix_upper_bound_increments_last_codepoint():
    assert _prefix_upper_bound("кабель") == "кабелэ"
    assert _prefix_upper_bound("") is None
    assert _prefix_upper_bound("z") == "{"


@pytest.mark.asyncio
async def test_startswith_range_matches_like(db_session):
    """Корректность _startswith_condition() (range по default-коллации) —
    должна ТОЧНО совпадать с LIKE 'prefix%' (см. докстринг функции, почему
    range, а не LIKE: с LIKE планировщик на 263 тыс. строк путает оценку
    кардинальности и уходит в полный скан)."""
    from sqlalchemy import func as sa_func

    a = _mk(db_session, name="Кабель медный ВВГ")
    b = _mk(db_session, name="кабель алюминиевый")  # тот же префикс, нижний регистр
    c = _mk(db_session, name="Кабельный канал")  # другой префикс после полного слова
    d = _mk(db_session, name="Труба медная")
    await db_session.commit()

    filters = ProductSearchFilters(search="кабель")
    cond = _startswith_condition(filters)
    rows = (await db_session.execute(select(Product.id).where(Product.id.in_(
        [a.id, b.id, c.id, d.id]
    )).where(cond))).scalars().all()
    ids = set(rows)
    like_rows = (await db_session.execute(select(Product.id).where(Product.id.in_(
        [a.id, b.id, c.id, d.id]
    )).where(sa_func.lower(Product.name).like("кабель%")))).scalars().all()
    assert ids == set(like_rows)
    assert a.id in ids and b.id in ids and c.id in ids
    assert d.id not in ids


@pytest.mark.asyncio
async def test_hybrid_ranking_startswith_first_then_alphabetical(db_session, monkeypatch):
    """При включённом гибридном режиме (total > RANK_FULL_THRESHOLD) порядок
    должен быть: сначала ВСЕ «начинается с запроса» (группа А, по алфавиту),
    потом остальные совпадения (группа Б, по алфавиту) — без similarity.

    ВЫЗЫВАЕТ _search_legacy_page НАПРЯМУЮ, НЕ search_products (владелец,
    28.10.2026, ревью «этап 0»): обычные словарные запросы вроде
    "хайбридтест" теперь идут через полнотекстовый поиск
    (_fetch_fts_page/search_products) — механизм startswith-группировки
    (_fetch_hybrid_page) из неё больше НЕ вызывается для таких запросов, но
    сам механизм остаётся в коде (используется для артикулов/коротких слов
    и как запасной путь) и тестируется напрямую здесь."""
    monkeypatch.setattr(product_search_module, "RANK_FULL_THRESHOLD", 0)

    # Уникальный выдуманный префикс (как test_pagination_total_and_offset
    # выше) — иначе на реальном/нагрузочном каталоге (263 тыс. строк) любое
    # обычное слово ("кабель", "болт") уже даёт тысячи посторонних совпадений
    # и ломает точные assert по total/порядку.
    startswith_b = _mk(db_session, name="Хайбридтест Б (начинается)")
    startswith_a = _mk(db_session, name="Хайбридтест А (начинается)")
    contains_only = _mk(db_session, name="Силовой хайбридтест в оболочке")
    unrelated = _mk(db_session, name="Труба стальная не хайбрид")
    await db_session.commit()

    filters = ProductSearchFilters(search="хайбридтест")
    items, total, capped = await product_search_module._search_legacy_page(
        db_session, filters, limit=50, offset=0, freshness_ctx=None,
    )
    ids_in_order = [p.id for p in items if p.id in {
        startswith_a.id, startswith_b.id, contains_only.id, unrelated.id,
    }]
    assert total == 3
    assert capped is False
    # Группа А (startswith) — по алфавиту раньше группы Б, внутри группы А
    # тоже по алфавиту (А раньше Б кириллически).
    assert ids_in_order == [startswith_a.id, startswith_b.id, contains_only.id]
    assert unrelated.id not in ids_in_order


@pytest.mark.asyncio
async def test_hybrid_ranking_pagination_no_dup_no_gap_across_groups(db_session, monkeypatch):
    """Пагинация должна быть сплошной через границу групп А/Б — ни дублей,
    ни пропусков, даже когда offset попадает РОВНО на стык (см. докстринг
    _fetch_hybrid_page — ветки k>0/k==0). _search_legacy_page напрямую —
    та же причина, что в тесте выше (владелец, 28.10.2026, ревью «этап
    0»)."""
    monkeypatch.setattr(product_search_module, "RANK_FULL_THRESHOLD", 0)

    # Уникальный выдуманный префикс — см. комментарий в тесте выше, почему
    # не обычное слово. 3 товара "начинается с" + 4 товара "только содержит"
    # — граница групп между 3-й и 4-й строкой при limit=3.
    startswith_ids = []
    for i in range(3):
        p = _mk(db_session, name=f"Хайбридкреп М{i} крепёжный")
        startswith_ids.append(p)
    contains_ids = []
    for i in range(4):
        p = _mk(db_session, name=f"Гайка с хайбридкреп-{i}")
        contains_ids.append(p)
    await db_session.commit()

    filters = ProductSearchFilters(search="хайбридкреп")
    seen: list[int] = []
    for offset in range(0, 7, 3):
        items, total, _ = await product_search_module._search_legacy_page(
            db_session, filters, limit=3, offset=offset, freshness_ctx=None,
        )
        seen.extend(p.id for p in items)
    assert total == 7
    assert len(seen) == len(set(seen)), "дубли через границу групп А/Б"
    expected_ids = {p.id for p in startswith_ids} | {p.id for p in contains_ids}
    assert set(seen) == expected_ids, "пропуски через границу групп А/Б"


# ── QA-находки 28.10.2026 (ревью «этап 0») ─────────────────────────────────

@pytest.mark.asyncio
async def test_product_out_serializes_null_price_shared_and_is_active(db_session):
    """(а) HTTP 500 на /api/products/page: 14 товаров в БД с
    price_shared IS NULL (напр. прод id 812302) — ProductOut.price_shared
    был НЕ-Optional bool, pydantic валидация падала. Чиним на уровне
    ProductOut (field_validator mode='before', None→False/True для
    price_shared/is_active), данные в БД не трогаем — тест создаёт товар
    с явным None в обоих полях и проверяет, что сериализация НЕ падает."""
    p = _mk(db_session, name="Товар с price_shared/is_active NULL")
    await db_session.commit()
    # ORM Column(default=False/True) подставляет дефолт при INSERT, даже
    # если явно присвоить None, ДО flush — реальные NULL-строки (14 на
    # деве, прод id 812302) появились из bulk-импорта МИМО ORM. Форсируем
    # тем же способом — прямым UPDATE, в обход Python-дефолта колонки.
    from sqlalchemy import text as _sa_text
    await db_session.execute(
        _sa_text("UPDATE products SET price_shared = NULL, is_active = NULL WHERE id = :pid"),
        {"pid": p.id},
    )
    await db_session.commit()
    await db_session.refresh(p)
    assert p.price_shared is None and p.is_active is None  # подтверждаем исходные NULL

    out = ProductOut.model_validate(p)
    assert out.price_shared is False
    assert out.is_active is True


@pytest.mark.asyncio
async def test_page_endpoint_does_not_500_on_null_bool_fields(db_session, client, auth_headers):
    """Тот же случай — через реальный HTTP-эндпоинт /api/products/page
    (владелец, QA 28.10.2026): без фикса — 500 ValidationError."""
    p = _mk(db_session, name="Огнетушитель порошковый 4 кг NULL-тест")
    await db_session.commit()
    from sqlalchemy import text as _sa_text
    await db_session.execute(
        _sa_text("UPDATE products SET price_shared = NULL WHERE id = :pid"), {"pid": p.id},
    )
    await db_session.commit()

    resp = await client.get(
        "/api/products/page",
        params={"search": "огнетушитель порошковый 4 кг"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_search_pure_punctuation_returns_empty_not_whole_table(db_session):
    """(б) search="%%%" (ни буквы, ни цифры) — ПУСТОЙ результат без
    похода в БД за полной таблицей (владелец, QA 28.10.2026: раньше
    required «повышался» из символов, которые сами по себе ничего не
    фильтруют → отдавало весь каталог, 26 349 на деве)."""
    _mk(db_session, name="Любой товар для контроля")
    await db_session.commit()

    filters = ProductSearchFilters(search="%%%")
    items, total, capped = await search_products(db_session, filters, limit=50, offset=0)
    assert total == 0
    assert items == []
    assert capped is False


@pytest.mark.asyncio
async def test_search_garbage_operators_with_letters_does_not_match_everything(db_session):
    """(б) search="a:b & | !(" — буквы в строке ЕСТЬ, но после очистки нет
    ни одного полезного required-токена → легаси-путь (не FTS без
    условия), и фаззи НЕ запускается (нет 3 букв подряд) — total остаётся
    маленьким/нулевым, не «848 посторонних» (владелец, QA 28.10.2026)."""
    _mk(db_session, name="Совершенно обычный товар без спецсимволов")
    await db_session.commit()

    filters = ProductSearchFilters(search="a:b & | !(")
    meta: dict = {}
    items, total, capped = await search_products(
        db_session, filters, limit=50, offset=0, result_meta=meta,
    )
    assert total == 0
    assert meta["fuzzy"] is False
