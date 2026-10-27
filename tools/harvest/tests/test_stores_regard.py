"""Парсинг сохранённых fixture-страниц regard.ru — без живых запросов."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import seller_inn_for
from tools.harvest.stores import regard

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_finds_offers():
    html = _read("regard_category.html")
    candidates = regard.parse_category_page(html)
    assert len(candidates) > 0
    for c in candidates:
        assert c["name"]
        assert c["url"].startswith("https://www.regard.ru/")


def test_parse_product_page_brand_and_manufacturer_article():
    html = _read("regard_product_1.html")
    url = "https://www.regard.ru/product/757301/x"
    enrichment = regard.parse_product_page(html, url)
    assert enrichment["jsonld_brand"] == {"@type": "Brand", "name": "Netac"}
    assert enrichment["manufacturer_article"] == "NTSHD4P32DP-16K"
    assert enrichment["store_sku"] == "757301"
    assert len(enrichment["characteristics"]) > 0


def test_manufacturer_article_comes_from_real_characteristic_not_description_split():
    html = _read("regard_product_2.html")
    url = "https://www.regard.ru/product/395210/x"
    enrichment = regard.parse_product_page(html, url)
    names = [c["name"].strip().lower() for c in enrichment["characteristics"]]
    assert "параметр 1" not in names
    assert any(n == "код производителя" for n in names) or enrichment["manufacturer_article"]


def test_no_placeholder_spec_names_in_parsed_characteristics():
    for fixture in ("regard_product_1.html", "regard_product_2.html"):
        html = _read(fixture)
        enrichment = regard.parse_product_page(html, "https://www.regard.ru/product/1/x")
        for c in enrichment["characteristics"]:
            name_lower = c["name"].strip().lower()
            assert not name_lower.startswith("параметр")
            assert not name_lower.startswith("спецификация")


def test_missing_country_origin_is_none_not_default():
    html = _read("regard_product_1.html")
    url = "https://www.regard.ru/product/757301/x"
    enrichment = regard.parse_product_page(html, url)
    candidate = {"name": "Оперативная память 16GB DDR4 Netac Shadow III", "url": url, "price": 15990.0, "photos": []}
    item = regard.build_item(candidate, enrichment, set())
    # Этот товар (ОЗУ) не несёт страну производства на странице — item не
    # должен подставлять "Россия"/любое умолчание.
    assert item["country_origin"] is None


def test_build_item_resolves_manufacturer_from_jsonld():
    html = _read("regard_product_1.html")
    url = "https://www.regard.ru/product/757301/x"
    enrichment = regard.parse_product_page(html, url)
    candidate = {"name": "Оперативная память 16GB DDR4 Netac Shadow III", "url": url, "price": 15990.0, "photos": []}
    item = regard.build_item(candidate, enrichment, set())
    assert item["manufacturer"] == "Netac"
    assert item["manufacturer_article"] == "NTSHD4P32DP-16K"
    assert item["store_article"] == "757301"


def test_seller_inn_matches_stores_dictionary_not_hardcoded():
    contracts = load_gala_contracts()
    url = "https://www.regard.ru/product/757301/x"
    expected = contracts.store_for_url(url)["inn"]
    assert seller_inn_for(url) == expected
