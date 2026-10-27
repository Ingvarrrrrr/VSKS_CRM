"""Парсинг сохранённых fixture-страниц kns.ru — без живых запросов."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import seller_inn_for
from tools.harvest.stores import kns

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_reads_real_goodslist():
    html = _read("kns_category.html")
    candidates = kns.parse_category_page(html)
    assert len(candidates) > 0
    for c in candidates:
        assert c["name"]
        assert c["product_url"].startswith("https://www.kns.ru/product/")
        assert c["url"].endswith("/characteristics/")


def test_brand_and_article_come_from_goodslist_not_default():
    html = _read("kns_category.html")
    candidates = kns.parse_category_page(html)
    with_brand = [c for c in candidates if c["brand"]]
    assert with_brand
    assert all(c["brand"] != "Производитель" for c in with_brand)


def test_category_always_needs_product_visit():
    html = _read("kns_category.html")
    candidates = kns.parse_category_page(html)
    assert all(kns.needs_product_visit(c) for c in candidates)


def test_parse_product_page_real_characteristics_not_placeholder():
    html = _read("kns_product_1.html")
    enrichment = kns.parse_product_page(html, "https://www.kns.ru/product/x/characteristics/")
    assert len(enrichment["characteristics"]) > 10
    for c in enrichment["characteristics"]:
        assert not c["name"].strip().lower().startswith("параметр")
    assert enrichment["manufacturer_article"]


def test_build_item_uses_pn_as_manufacturer_article():
    html = _read("kns_category.html")
    candidates = kns.parse_category_page(html)
    enrichment = kns.parse_product_page(_read("kns_product_1.html"), candidates[0]["url"])
    item = kns.build_item(candidates[0], enrichment, set())
    assert item["manufacturer"]
    assert item["manufacturer_article"]
    assert item["source_url"] == candidates[0]["product_url"]


def test_second_product_fixture_also_parses():
    html = _read("kns_product_2.html")
    enrichment = kns.parse_product_page(html, "https://www.kns.ru/product/y/characteristics/")
    assert len(enrichment["characteristics"]) > 0


def test_seller_inn_matches_stores_dictionary():
    contracts = load_gala_contracts()
    url = "https://www.kns.ru/product/x/"
    expected = contracts.store_for_url(url)["inn"]
    assert seller_inn_for(url) == expected
