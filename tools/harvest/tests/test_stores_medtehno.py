"""Парсинг сохранённых fixture-страниц medtehno.ru — без живых запросов."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import seller_inn_for
from tools.harvest.stores import medtehno

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_finds_product_links_and_skips_brand_pages():
    html = _read("medtehno_category.html")
    candidates = medtehno.parse_category_page(html)
    assert len(candidates) > 0
    assert all("/brand-" not in c["url"] for c in candidates)


def test_category_always_needs_product_visit():
    html = _read("medtehno_category.html")
    candidates = medtehno.parse_category_page(html)
    assert all(medtehno.needs_product_visit(c) for c in candidates)


def test_parse_product_page_real_table_characteristics():
    html = _read("medtehno_product_1.html")
    enrichment = medtehno.parse_product_page(html, "https://www.medtehno.ru/catalog/x/")
    assert enrichment["name"]
    assert enrichment["price"] is not None
    assert len(enrichment["characteristics"]) > 10
    for c in enrichment["characteristics"]:
        assert not c["name"].strip().lower().startswith("параметр")


def test_second_fixture_characteristics_cleaned_of_nbsp():
    html = _read("medtehno_product_2.html")
    enrichment = medtehno.parse_product_page(html, "https://www.medtehno.ru/catalog/y/")
    assert len(enrichment["characteristics"]) > 0
    for c in enrichment["characteristics"]:
        assert "&nbsp;" not in c["value"]
        assert "\xa0" not in c["value"]


def test_build_item_manufacturer_article_never_fabricated():
    html = _read("medtehno_product_1.html")
    enrichment = medtehno.parse_product_page(html, "https://www.medtehno.ru/catalog/x/")
    item = medtehno.build_item({"url": "https://www.medtehno.ru/catalog/x/"}, enrichment, set())
    assert item["manufacturer_article"] is None
    assert item["store_article"] == "x"


def test_seller_inn_matches_stores_dictionary():
    contracts = load_gala_contracts()
    url = "https://www.medtehno.ru/catalog/x/"
    expected = contracts.store_for_url(url)["inn"]
    assert seller_inn_for(url) == expected
