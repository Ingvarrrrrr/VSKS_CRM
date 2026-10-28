"""Тесты «живого поиска товара в магазинах» (этап 1, владелец, 28.10.2026).

Разбор фикстур — по живым ответам (backend/tests/fixtures/store_search/),
снятым живыми запросами (см. отчёт сессии): kuvalda «перфоратор», safe
«шкаф», chipdip «резистор», sima_land «перчатки», magazin01 «огнетушитель»
(+ 1 страница товара для цены), promalper «карабин». Сервис (service.py) —
с подменённым HTTP-клиентом (monkeypatch, respx в проекте не установлен)."""
import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.product_query_parse import parse_query
from app.services.store_search import (
    avtoall, chipdip, emex, ice_age, kns, kuvalda, magazin01, medtehno, promalper, regard, safe, sima_land,
)
from app.services.store_search.price_from_product_page import extract_price_and_image
from app.services.store_search import service as store_search_service
from app.services.store_search.base import StoreOffer
from app.services.store_search.relevance import filter_relevant_offers

FIXTURES = Path(__file__).parent / "fixtures" / "store_search"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Разбор фикстур каждого магазина
# ---------------------------------------------------------------------------

def test_kuvalda_parses_fixture():
    offers = kuvalda.parse_search_html(_read("kuvalda.html"))
    assert len(offers) >= 10
    first = offers[0]
    assert first.name
    assert first.url.startswith("https://www.kuvalda.ru/")
    assert any(o.price is not None for o in offers)


def test_safe_parses_fixture():
    offers = safe.parse_search_html(_read("safe.html"))
    assert len(offers) >= 5
    priced = [o for o in offers if o.price is not None]
    assert priced, "хотя бы одно предложение safe.ru должно нести цену"
    assert all(o.url.startswith("https://www.safe.ru/products/") for o in priced)
    assert any(o.manufacturer for o in priced)


def test_chipdip_parses_fixture():
    offers = chipdip.parse_search_html(_read("chipdip.html"))
    assert len(offers) >= 10
    assert all(o.url.startswith("https://www.chipdip.ru/product/") for o in offers)
    assert any(o.manufacturer == "Yageo" for o in offers)
    assert any(o.price is not None for o in offers)


def test_sima_land_parses_fixture():
    offers = sima_land.parse_search_json(_read("sima_land.json"))
    assert len(offers) >= 5
    assert all(o.store_article for o in offers)
    assert any(o.price is not None for o in offers)


def test_magazin01_parses_search_links_without_price():
    links = magazin01.parse_search_html_links(_read("magazin01.html"))
    assert len(links) >= 5
    # Только товарные ссылки (блог отфильтрован).
    assert all("/product/" in u for u, _ in links)


def test_magazin01_product_page_gives_price_and_meta():
    html = _read("magazin01_product.html")
    price, image = extract_price_and_image(html)
    assert price == Decimal("959")
    assert image
    name, manufacturer, sku = magazin01._parse_product_meta(html, "fallback")
    assert "огнетушителя" in name.lower()
    assert manufacturer == "НПО Пульс"
    assert sku == "5502010200004"


def test_promalper_parses_fixture_with_inline_price():
    offers = promalper.parse_search_json(_read("promalper.json"))
    assert len(offers) >= 5
    assert all(o.price is not None for o in offers), "promalper отдаёт цену прямо в JSON поиска"
    assert offers[0].price > 0


# ---------------------------------------------------------------------------
# Вторая волна адаптеров (владелец, 28.10.2026): regard, medtehno, ice_age,
# avtoall, kns, emex — разбор фикстур.
# ---------------------------------------------------------------------------

def test_regard_parses_fixture_and_falls_back_to_search_page_url():
    offers = regard.parse_search_json(_read("regard.json"), "монитор")
    assert len(offers) >= 5
    # Карточка товара без браузерной cookie-сессии недоступна (см. docstring
    # regard.py) — все предложения ведут на страницу поиска с тем же запросом.
    assert all(o.url == offers[0].url for o in offers)
    assert offers[0].url == "https://www.regard.ru/catalog?search=%D0%BC%D0%BE%D0%BD%D0%B8%D1%82%D0%BE%D1%80"
    assert any(o.manufacturer for o in offers)
    assert any(o.price is not None for o in offers)


def test_medtehno_parses_fixture():
    offers = medtehno.parse_search_json(_read("medtehno.json"))
    assert len(offers) >= 10
    assert all(o.url.startswith("https://www.medtehno.ru/") for o in offers)
    assert any(o.manufacturer for o in offers)
    assert any(o.price is not None for o in offers)


def test_ice_age_parses_fixture():
    offers = ice_age.parse_search_json(_read("ice_age.json"))
    assert len(offers) >= 10
    assert all(o.url.startswith("https://ice-age.ru/product/") for o in offers)
    assert any(o.price is not None for o in offers)


def test_avtoall_parses_fixture_and_falls_back_to_search_page_url():
    offers = avtoall.parse_search_json(_read("avtoall.json"), "масло 5w40")
    assert len(offers) >= 10
    # Карточки товара без доступного прямого URL — все предложения ведут
    # на страницу поиска с тем же запросом (см. docstring avtoall.py).
    assert all(o.url == offers[0].url for o in offers)
    assert "avtoall.ru/search/" in offers[0].url
    assert any(o.price is not None for o in offers)


def test_avtoall_skips_category_suggestions():
    raw = json.dumps({"status": "success", "data": [
        {"isCategory": True, "name": "Категория", "avgPrice": "", "picUrl": None, "value": "1;;"},
        {"isCategory": False, "name": "Масло X", "avgPrice": "1 000 ₽", "picUrl": None, "value": "2;;"},
    ]})
    offers = avtoall.parse_search_json(raw, "масло")
    assert len(offers) == 1
    assert offers[0].name == "Масло X"


def test_kns_parses_fixture():
    offers = kns.parse_search_html(_read("kns.html"))
    assert len(offers) >= 10
    assert all(o.url.startswith("https://www.kns.ru/product/") for o in offers)
    assert all(o.price is not None for o in offers)


def test_emex_parses_fixture_for_article_query():
    offers = emex.parse_search_json(_read("emex.json"))
    assert len(offers) >= 3
    assert all(o.url.startswith("https://emex.ru/0510000410/") for o in offers)
    assert any(o.price is not None for o in offers)
    assert any(o.manufacturer for o in offers)


def test_emex_no_results_for_free_text():
    raw = json.dumps({"searchResult": {"noResults": True}, "errorMessage": ""})
    assert emex.parse_search_json(raw) == []


def test_emex_looks_like_article_query():
    assert emex.looks_like_article_query("0510000410") is True
    assert emex.looks_like_article_query("1942003") is True
    assert emex.looks_like_article_query("масло 5w40") is False
    assert emex.looks_like_article_query("огнетушитель") is False


@pytest.mark.asyncio
async def test_emex_not_queried_for_ordinary_text(monkeypatch):
    """service.search_stores не идёт в сеть за emex, если запрос не похож
    на артикул (ПРАВИЛО №6 — тот же признак, что у встроенного поиска)."""
    called = {"n": 0}

    class _SpyEmex:
        key = "emex"
        domain = "emex.ru"

        async def search(self, client, query, limit):
            called["n"] += 1
            return []

    monkeypatch.setitem(store_search_service.ADAPTERS, "emex", _SpyEmex())
    result = await store_search_service.search_stores("огнетушитель", stores=["emex"])
    assert called["n"] == 0
    assert result["stores"] == []  # emex отфильтрован из списка магазинов вовсе


@pytest.mark.asyncio
async def test_emex_queried_for_article_like_text(monkeypatch):
    called = {"n": 0}

    class _SpyEmex:
        key = "emex"
        domain = "emex.ru"

        async def search(self, client, query, limit):
            called["n"] += 1
            return []

    monkeypatch.setitem(store_search_service.ADAPTERS, "emex", _SpyEmex())
    result = await store_search_service.search_stores("0510000410", stores=["emex"])
    assert called["n"] == 1
    assert result["stores"][0]["key"] == "emex"


# ---------------------------------------------------------------------------
# Сервис — кэш / rate-limit / устойчивость к таймауту одного магазина
# ---------------------------------------------------------------------------

class _FakeOffer:
    def __init__(self, name="Товар", price=None):
        self.name = name
        self.price = price
        self.store_name = "Тест"


class _SlowAdapter:
    key = "slow"
    domain = "slow.example"

    async def search(self, client, query, limit):
        await asyncio.sleep(10)
        return []


class _FastAdapter:
    key = "fast"
    domain = "fast.example"

    def __init__(self):
        self.calls = 0

    async def search(self, client, query, limit):
        self.calls += 1
        from app.services.store_search.base import StoreOffer
        return [StoreOffer(
            store_key="fast", store_name="Fast Store", seller_inn=None,
            name=f"Товар {query}", price=Decimal("100"), url="https://fast.example/1",
        )]


@pytest.fixture(autouse=True)
def _reset_service_state():
    store_search_service._cache.clear()
    store_search_service._rate_log.clear()
    yield
    store_search_service._cache.clear()
    store_search_service._rate_log.clear()


@pytest.mark.asyncio
async def test_timeout_in_one_store_does_not_break_others(monkeypatch):
    fast = _FastAdapter()
    monkeypatch.setitem(store_search_service.ADAPTERS, "slow", _SlowAdapter())
    monkeypatch.setitem(store_search_service.ADAPTERS, "fast", fast)
    monkeypatch.setattr(store_search_service, "PER_STORE_TIMEOUT_SECONDS", 0.2)

    result = await store_search_service.search_stores("перфоратор", stores=["slow", "fast"])

    statuses = {s["key"]: s["status"] for s in result["stores"]}
    assert statuses["slow"] == "timeout"
    assert statuses["fast"] == "ok"
    assert any(o.store_key == "fast" for o in result["offers"])


@pytest.mark.asyncio
async def test_cache_avoids_second_call(monkeypatch):
    fast = _FastAdapter()
    monkeypatch.setitem(store_search_service.ADAPTERS, "fast", fast)

    await store_search_service.search_stores("дрель", stores=["fast"])
    await store_search_service.search_stores("дрель", stores=["fast"])

    assert fast.calls == 1, "второй одинаковый запрос должен взяться из кэша"


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_threshold(monkeypatch):
    fast = _FastAdapter()
    monkeypatch.setitem(store_search_service.ADAPTERS, "fast", fast)
    monkeypatch.setattr(store_search_service, "RATE_LIMIT_PER_MINUTE", 2)

    # Разные запросы — кэш не вмешивается, лимит считает реальные обращения.
    for i in range(2):
        r = await store_search_service.search_stores(f"товар{i}", stores=["fast"])
        assert r["stores"][0]["status"] == "ok"

    r3 = await store_search_service.search_stores("товар-третий", stores=["fast"])
    assert r3["stores"][0]["status"] == "rate_limited"


@pytest.mark.asyncio
async def test_clean_query_falls_back_to_raw_when_parse_empty():
    # "и" — только стоп-слово, required пуст → исходная строка используется.
    cleaned = store_search_service.clean_query("и")
    assert cleaned == "и"


# ---------------------------------------------------------------------------
# clean_query — дефект владельца 29.10.2026: «монитор 27» терял слово
# «монитор» (вид товара не в словаре product_name_signature → required несёт
# только цифру). Правило: вид распознан → required (бренд+вид+модель+
# величины) как есть; вид НЕ распознан → все значимые слова фразы без
# стоп-слов (не только цифры); пусто/только цифры → исходная строка.
# ---------------------------------------------------------------------------

def test_clean_query_keeps_unrecognized_type_word():
    # "монитор" нет в словаре product_name_signature — без фикса required
    # нёс только цифру "27", слово "монитор" терялось полностью.
    cleaned = store_search_service.clean_query("монитор 27")
    assert "монитор" in cleaned
    assert "27" in cleaned


def test_clean_query_keeps_both_words_when_type_not_in_dictionary():
    # "пускатель" (магнитный пускатель) не в словаре вида товара — фраза
    # должна дойти целиком, не только первое слово.
    cleaned = store_search_service.clean_query("пускатель магнитный")
    assert cleaned == "пускатель магнитный"


def test_clean_query_recognized_type_drops_filler_word():
    # "болгарка" — распознанный вид (канон "шлифмашина"), required несёт
    # вид+модель; "с" (предлог) и общее слово "регулировкой" не идут в
    # очищенный запрос.
    cleaned = store_search_service.clean_query("болгарка макита 125 с регулировкой")
    assert "болгарка" in cleaned
    assert "регулировкой" not in cleaned
    assert cleaned.split() != ["с"]


class _FakeBrandDictionary:
    """Контракт `.find_in_name(name) -> str | None`, тот же что у
    ManufacturerBrandDictionary (product_query_parse.py) — здесь без похода
    в БД, только одно известное соответствие для теста ниже."""

    def find_in_name(self, name: str):
        if "макита" in (name or "").lower():
            return "Makita"
        return None


def test_clean_query_recognizes_brand_with_dictionary():
    # Дефект 29.10.2026: clean_query() строила запрос БЕЗ словаря брендов
    # (parse_query() без brand_dictionary) — «болгарка макита 125» уходила в
    # магазины без бренда "Makita" вовсе. С переданным словарём (тот же,
    # что search_stores() получает через get_manufacturer_brand_dictionary,
    # ПРАВИЛО №6) бренд — в каноническом написании из словаря.
    cleaned = store_search_service.clean_query(
        "болгарка макита 125 с регулировкой", brand_dictionary=_FakeBrandDictionary(),
    )
    assert "Makita" in cleaned
    assert "125" in cleaned
    assert " с " not in f" {cleaned} "


def test_clean_query_article_stays_as_is():
    cleaned = store_search_service.clean_query("0510000410")
    assert cleaned == "0510000410"


def test_clean_query_never_only_digits():
    # product_type не распознан, фраза состоит ТОЛЬКО из цифр после чистки
    # (гипотетически) — защита отдаёт исходную строку целиком, не голые цифры.
    cleaned = store_search_service.clean_query("27")
    assert cleaned == "27"  # тут raw и так "27" — проверяем, что не падает/не пустеет


# ---------------------------------------------------------------------------
# Роут — доступ только вошедшим, валидация q
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_search_requires_auth(client):
    resp = await client.get("/api/products/store-search", params={"q": "дрель"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_store_search_rejects_empty_query(client, auth_headers):
    resp = await client.get("/api/products/store-search", params={"q": "   "}, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_store_search_rejects_unknown_store(client, auth_headers):
    resp = await client.get(
        "/api/products/store-search", params={"q": "дрель", "stores": "no-such-store"}, headers=auth_headers,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# relevance.filter_relevant_offers — QA 29.10.2026: нишевые магазины
# (promalper/ice_age/medtehno) на «пускатель магнитный» отдавали случайные
# товары своей популярной выдачи («Магнитная игра», «Браслет магнитный» —
# совпало только одно слово «магнитный»); фильтр должен выбросить их и
# оставить настоящие пускатели.
# ---------------------------------------------------------------------------

def _offer(name: str) -> StoreOffer:
    return StoreOffer(
        store_key="test_store", store_name="Тест", seller_inn=None,
        name=name, price=Decimal("100"), url="https://example.com/1",
    )


@pytest.mark.asyncio
async def test_filter_relevant_offers_drops_unrelated_offers_without_db_match(db_session):
    parsed = parse_query("пускатель магнитный")
    offers = [
        _offer("Пускатель магнитный ПМЛ-1100"),
        _offer("Магнитная игра для малышей"),
        _offer("Браслет магнитный медный"),
        _offer("Конструктор магнитный Magformers"),
    ]
    kept = await filter_relevant_offers(offers, parsed, db_session)
    names = [o.name for o in kept]
    assert "Пускатель магнитный ПМЛ-1100" in names
    assert "Магнитная игра для малышей" not in names
    assert "Браслет магнитный медный" not in names
    assert "Конструктор магнитный Magformers" not in names


@pytest.mark.asyncio
async def test_filter_relevant_offers_keeps_relevant_offers(db_session):
    # Проверка «по основам слов» (не литерально) — словоформы "пускатели"/
    # "магнитные" (мн. число) должны стеммиться до того же корня, что
    # "пускатель"/"магнитный" из запроса.
    parsed = parse_query("пускатель магнитный")
    offers = [
        _offer("Пускатель магнитный ПМЛ-1100 220В"),
        _offer("Пускатели магнитные ПМЕ-211, упаковка 10 шт"),
    ]
    kept = await filter_relevant_offers(offers, parsed, db_session)
    assert len(kept) == 2


@pytest.mark.asyncio
async def test_filter_relevant_offers_type_match_keeps_different_wording():
    # "болгарка" распознанный вид (канон "шлифмашина") — название с другим
    # написанием того же вида (синоним из словаря) остаётся даже без
    # большинства слов фразы, см. docstring relevance.py.
    parsed = parse_query("болгарка макита 125")
    offers = [_offer("Угловая шлифмашина Makita 9558HNG 125мм")]
    kept = await filter_relevant_offers(offers, parsed, None)
    assert len(kept) == 1


@pytest.mark.asyncio
async def test_filter_relevant_offers_without_db_degrades_to_literal_words():
    parsed = parse_query("пускатель магнитный")
    offers = [_offer("Пускатель магнитный ПМЛ-1100"), _offer("Браслет магнитный медный")]
    kept = await filter_relevant_offers(offers, parsed, None)
    names = [o.name for o in kept]
    assert "Пускатель магнитный ПМЛ-1100" in names
    assert "Браслет магнитный медный" not in names
