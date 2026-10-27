"""Парсинг сохранённых fixture-страниц promalper.com — без живых
запросов."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import seller_inn_for
from tools.harvest.stores import promalper

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_finds_product_links():
    html = _read("promalper_category.html")
    candidates = promalper.parse_category_page(html)
    assert len(candidates) > 0
    for c in candidates:
        assert c["url"].startswith("https://promalper.com/product/")


def test_category_always_needs_product_visit():
    html = _read("promalper_category.html")
    candidates = promalper.parse_category_page(html)
    assert all(promalper.needs_product_visit(c) for c in candidates)


def test_parse_product_page_brand_and_country_from_attributes_table():
    html = _read("promalper_product_1.html")
    enrichment = promalper.parse_product_page(html, "https://promalper.com/product/x/")
    assert enrichment["jsonld_brand"] == "Camp"
    assert enrichment["country_origin"] == "Италия"
    assert enrichment["price"] == 690.0


def test_second_product_no_default_country_fallback():
    html = _read("promalper_product_2.html")
    enrichment = promalper.parse_product_page(html, "https://promalper.com/product/y/")
    assert enrichment["jsonld_brand"] == "DPS"
    assert enrichment["country_origin"] == "Россия"
    assert enrichment["store_article"] == "4651"


def test_build_item_manufacturer_article_never_fabricated():
    html = _read("promalper_product_1.html")
    enrichment = promalper.parse_product_page(html, "https://promalper.com/product/x/")
    item = promalper.build_item({"url": "https://promalper.com/product/x/"}, enrichment, set())
    assert item["manufacturer_article"] is None
    assert item["manufacturer"] == "Camp"


def test_seller_inn_matches_stores_dictionary():
    contracts = load_gala_contracts()
    url = "https://promalper.com/product/x/"
    expected = contracts.store_for_url(url)["inn"]
    assert seller_inn_for(url) == expected
