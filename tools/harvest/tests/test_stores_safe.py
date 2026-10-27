"""Парсинг сохранённых fixture-страниц safe.ru — без живых запросов."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import seller_inn_for
from tools.harvest.stores import safe

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_finds_product_links():
    html = _read("safe_category.html")
    candidates = safe.parse_category_page(html)
    assert len(candidates) > 0
    for c in candidates:
        assert c["url"].startswith("https://www.safe.ru/products/")


def test_category_always_needs_product_visit():
    html = _read("safe_category.html")
    candidates = safe.parse_category_page(html)
    assert all(safe.needs_product_visit(c) for c in candidates)


def test_parse_product_page_brand_and_country_from_table_not_hardcoded():
    html = _read("safe_product_1.html")
    enrichment = safe.parse_product_page(html, "https://www.safe.ru/products/x/")
    assert enrichment["jsonld_brand"] == "ПРОМЕТ"
    # Старый сборщик хардкодил "ПРАКТИК (ПРОМЕТ)" — реальное поле отдаёт
    # просто "ПРОМЕТ", не это составное имя.
    assert enrichment["jsonld_brand"] != "ПРАКТИК (ПРОМЕТ)"
    assert enrichment["country_origin"] == "Россия"
    assert enrichment["price"] == 4750.0
    assert enrichment["store_article"]


def test_second_fixture_also_real_data():
    html = _read("safe_product_2.html")
    enrichment = safe.parse_product_page(html, "https://www.safe.ru/products/y/")
    assert enrichment["jsonld_brand"] == "ПРОМЕТ"
    assert len(enrichment["characteristics"]) >= 5


def test_build_item_manufacturer_article_never_fabricated_from_slug():
    html = _read("safe_product_1.html")
    enrichment = safe.parse_product_page(html, "https://www.safe.ru/products/x/")
    item = safe.build_item({"url": "https://www.safe.ru/products/x/"}, enrichment, set())
    assert item["manufacturer_article"] is None
    assert item["manufacturer"] == "ПРОМЕТ"


def test_seller_inn_matches_stores_dictionary():
    contracts = load_gala_contracts()
    url = "https://www.safe.ru/products/x/"
    expected = contracts.store_for_url(url)["inn"]
    assert seller_inn_for(url) == expected
