"""Парсинг сохранённых fixture-страниц ice-age.ru (JSON InSales) — без
живых запросов."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import seller_inn_for
from tools.harvest.stores import ice_age

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_sitemap_appends_json_suffix():
    xml_text = _read("ice_age_category.xml")
    candidates = ice_age.parse_category_page(xml_text)
    assert len(candidates) > 0
    for c in candidates:
        assert c["url"].endswith(".json")
        assert not c["product_url"].endswith(".json")


def test_category_always_needs_product_visit():
    xml_text = _read("ice_age_category.xml")
    candidates = ice_age.parse_category_page(xml_text)
    assert all(ice_age.needs_product_visit(c) for c in candidates)


def test_parse_product_page_brand_from_properties_not_name_heuristic():
    raw = _read("ice_age_product_1.json")
    enrichment = ice_age.parse_product_page(raw, "https://ice-age.ru/product/x.json")
    assert enrichment["jsonld_brand"] == "CAMP"
    assert enrichment["name"]
    assert len(enrichment["characteristics"]) > 0


def test_hidden_status_property_excluded_from_characteristics():
    for fixture in ("ice_age_product_1.json", "ice_age_product_2.json"):
        raw = _read(fixture)
        enrichment = ice_age.parse_product_page(raw, "https://ice-age.ru/product/x.json")
        names = [c["name"].lower() for c in enrichment["characteristics"]]
        assert "статус" not in names


def test_build_item_links_to_human_readable_url_not_json():
    raw = _read("ice_age_product_1.json")
    enrichment = ice_age.parse_product_page(raw, "https://ice-age.ru/product/molotok-skalnyy-brenta.json")
    candidate = {
        "url": "https://ice-age.ru/product/molotok-skalnyy-brenta.json",
        "product_url": "https://ice-age.ru/product/molotok-skalnyy-brenta",
    }
    item = ice_age.build_item(candidate, enrichment, set())
    assert item["source_url"] == "https://ice-age.ru/product/molotok-skalnyy-brenta"
    assert item["manufacturer"] == "CAMP"


def test_seller_inn_matches_stores_dictionary():
    contracts = load_gala_contracts()
    url = "https://ice-age.ru/product/x"
    expected = contracts.store_for_url(url)["inn"]
    assert seller_inn_for(url) == expected
