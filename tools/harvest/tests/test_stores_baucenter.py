"""Парсинг сохранённых fixture-страниц baucenter.ru (Next.js data-JSON) —
без живых запросов."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import seller_inn_for
from tools.harvest.stores import baucenter

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_finds_products_with_brand():
    raw = _read("baucenter_category.json")
    candidates = baucenter.parse_category_page(raw)
    assert len(candidates) > 0
    for c in candidates:
        assert c["name"]
        assert c["url"].startswith("https://baucenter.ru/")
    assert any(c.get("brand") for c in candidates)


def test_category_always_needs_product_visit():
    raw = _read("baucenter_category.json")
    candidates = baucenter.parse_category_page(raw)
    assert all(baucenter.needs_product_visit(c) for c in candidates)


def test_price_converted_from_kopecks():
    raw = _read("baucenter_category.json")
    candidates = baucenter.parse_category_page(raw)
    priced = [c for c in candidates if c["price"] is not None]
    assert priced
    # Цена в разделе не должна быть "сырыми" копейками (три порядка больше).
    assert all(c["price"] < 100000 for c in priced)


def test_parse_product_page_characteristics_and_country():
    html_text = _read("baucenter_product_1.json")
    enrichment = baucenter.parse_product_page(html_text, "https://baucenter.ru/product/x/")
    assert len(enrichment["characteristics"]) > 0
    assert enrichment["country_origin"]
    assert enrichment["brand"]


def test_no_placeholder_characteristic_names():
    for fixture in ("baucenter_product_1.json", "baucenter_product_2.json"):
        html_text = _read(fixture)
        enrichment = baucenter.parse_product_page(html_text, "https://baucenter.ru/product/x/")
        for c in enrichment["characteristics"]:
            assert not c["name"].strip().lower().startswith("параметр")


def test_build_item_manufacturer_article_never_fabricated():
    raw = _read("baucenter_category.json")
    candidates = baucenter.parse_category_page(raw)
    html_text = _read("baucenter_product_1.json")
    enrichment = baucenter.parse_product_page(html_text, candidates[0]["url"])
    item = baucenter.build_item(candidates[0], enrichment, set())
    assert item["manufacturer_article"] is None


def test_seller_inn_matches_stores_dictionary():
    contracts = load_gala_contracts()
    url = "https://baucenter.ru/product/x-ctg-1-2-3-511690211/"
    expected = contracts.store_for_url(url)["inn"]
    assert seller_inn_for(url) == expected
