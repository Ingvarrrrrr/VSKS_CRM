"""Парсинг сохранённых fixture-страниц k-spasatel.ru — без живых
запросов."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import seller_inn_for
from tools.harvest.stores import k_spasatel

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_finds_product_links():
    html = _read("k_spasatel_category.html")
    candidates = k_spasatel.parse_category_page(html)
    assert len(candidates) > 0
    for c in candidates:
        assert c["url"].startswith("https://k-spasatel.ru/")


def test_category_always_needs_product_visit():
    html = _read("k_spasatel_category.html")
    candidates = k_spasatel.parse_category_page(html)
    assert all(k_spasatel.needs_product_visit(c) for c in candidates)


def test_parse_product_page_1_paragraph_format_characteristics():
    html = _read("k_spasatel_product_1.html")
    enrichment = k_spasatel.parse_product_page(html, "https://k-spasatel.ru/x")
    assert enrichment["name"]
    assert enrichment["store_article"] == "302614"
    assert len(enrichment["characteristics"]) > 0


def test_parse_product_page_2_table_format_characteristics():
    html = _read("k_spasatel_product_2.html")
    enrichment = k_spasatel.parse_product_page(html, "https://k-spasatel.ru/y")
    assert enrichment["name"]
    assert enrichment["store_article"] == "988011"
    assert len(enrichment["characteristics"]) > 0


def test_price_on_request_is_none_not_guessed():
    for fixture in ("k_spasatel_product_1.html", "k_spasatel_product_2.html"):
        html = _read(fixture)
        enrichment = k_spasatel.parse_product_page(html, "https://k-spasatel.ru/z")
        assert enrichment["price"] is None


def test_build_item_manufacturer_article_never_fabricated():
    html = _read("k_spasatel_product_1.html")
    enrichment = k_spasatel.parse_product_page(html, "https://k-spasatel.ru/x")
    item = k_spasatel.build_item({"url": "https://k-spasatel.ru/x"}, enrichment, set())
    assert item["manufacturer_article"] is None
    assert item["store_article"] == "302614"


def test_seller_inn_matches_stores_dictionary():
    contracts = load_gala_contracts()
    url = "https://k-spasatel.ru/dlja-spasenija-na-vode/lodki/x"
    expected = contracts.store_for_url(url)["inn"]
    assert seller_inn_for(url) == expected
