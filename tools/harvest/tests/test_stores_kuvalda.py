"""Парсинг сохранённых fixture-страниц kuvalda.ru — без живых запросов."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import resolve_manufacturer, seller_inn_for
from tools.harvest.stores import kuvalda

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_finds_offers():
    html = _read("kuvalda_category.html")
    candidates = kuvalda.parse_category_page(html)
    assert len(candidates) > 0
    for c in candidates:
        assert c["name"]
        assert c["url"].startswith("https://www.kuvalda.ru/")


def test_category_page_never_needs_no_product_visit():
    html = _read("kuvalda_category.html")
    candidates = kuvalda.parse_category_page(html)
    assert all(kuvalda.needs_product_visit(c) for c in candidates)


def test_parse_product_page_brand_from_jsonld():
    html = _read("kuvalda_product_1.html")
    enrichment = kuvalda.parse_product_page(html, "https://www.kuvalda.ru/catalog/9045/product-23241/")
    assert enrichment["jsonld_brand"] == {"@type": "Brand", "name": "MAKITA"}
    assert enrichment["manufacturer_article"] == "DP4010"
    assert len(enrichment["characteristics"]) > 0


def test_no_placeholder_spec_names_in_parsed_characteristics():
    for fixture in ("kuvalda_product_1.html", "kuvalda_product_2.html"):
        html = _read(fixture)
        enrichment = kuvalda.parse_product_page(html, "https://www.kuvalda.ru/catalog/9045/x/")
        for c in enrichment["characteristics"]:
            name_lower = c["name"].strip().lower()
            assert not name_lower.startswith("параметр")
            assert not name_lower.startswith("спецификация")


def test_build_item_resolves_manufacturer_from_jsonld_not_name_heuristic():
    html = _read("kuvalda_product_1.html")
    url = "https://www.kuvalda.ru/catalog/9045/product-23241/"
    enrichment = kuvalda.parse_product_page(html, url)
    candidate = {"name": "Дрель безударная сетевая MAKITA DP 4010", "url": url, "price": 11699.0, "photos": [], "source_id": "23241"}
    item = kuvalda.build_item(candidate, enrichment, set())
    assert item["manufacturer"] == "MAKITA"
    assert item["manufacturer_article"] == "DP4010"


def test_seller_inn_matches_stores_dictionary_not_hardcoded():
    # ПРАВИЛО №6 — сверяем с тем, что реально возвращает store_for_url, а не
    # с захардкоженной строкой, чтобы тест не разошёлся со справочником.
    contracts = load_gala_contracts()
    url = "https://www.kuvalda.ru/catalog/9045/product-23241/"
    expected = contracts.store_for_url(url)["inn"]
    assert seller_inn_for(url) == expected


def test_resolve_manufacturer_never_picks_bogus_from_name_alone():
    # Без JSON-LD (аргумент brand=None) и без характеристик — не
    # придумывать бренд по первому слову названия (брак старого сборщика).
    result = resolve_manufacturer("Лестница алюминиевая раздвижная трехсекционная", None, [], set())
    assert result is None
