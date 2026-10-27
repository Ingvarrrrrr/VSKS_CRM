"""Парсинг сохранённой fixture-страницы sima-land.ru (JSON API) — без живых
запросов. sima-land отдаёт всю карточку в разделе, поэтому у него нет
отдельных fixture-страниц товара (см. докстринг stores/sima_land.py)."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import seller_inn_for
from tools.harvest.stores import sima_land

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_finds_items():
    raw = _read("sima_category.json")
    candidates = sima_land.parse_category_page(raw)
    assert len(candidates) > 0
    for c in candidates:
        assert c["name"]
        assert c["url"].startswith("https://www.sima-land.ru/")
        assert c["store_article"]


def test_category_never_needs_product_visit():
    raw = _read("sima_category.json")
    candidates = sima_land.parse_category_page(raw)
    assert all(sima_land.needs_product_visit(c) is False for c in candidates)


def test_build_item_uses_trademark_not_default_brand():
    raw = _read("sima_category.json")
    candidates = sima_land.parse_category_page(raw)
    with_brand = [c for c in candidates if c.get("trademark_name")]
    assert with_brand, "фикстура должна содержать хотя бы один товар с trademark"
    item = sima_land.build_item(with_brand[0], {}, set())
    assert item["manufacturer"] == with_brand[0]["trademark_name"]
    # Старый сборщик подставлял "Сима-ленд" по умолчанию при отсутствии
    # trademark — это брак, manufacturer без trademark должен быть None.
    no_brand_candidate = dict(with_brand[0])
    no_brand_candidate["trademark_name"] = None
    item_no_brand = sima_land.build_item(no_brand_candidate, {}, set())
    assert item_no_brand["manufacturer"] != "Сима-ленд"


def test_build_item_manufacturer_article_never_fabricated():
    raw = _read("sima_category.json")
    candidates = sima_land.parse_category_page(raw)
    item = sima_land.build_item(candidates[0], {}, set())
    assert item["manufacturer_article"] is None


def test_build_item_country_from_api_field_only():
    raw = _read("sima_category.json")
    candidates = sima_land.parse_category_page(raw)
    with_country = [c for c in candidates if c.get("country_name")]
    assert with_country
    item = sima_land.build_item(with_country[0], {}, set())
    assert item["country_origin"] == with_country[0]["country_name"]


def test_seller_inn_matches_stores_dictionary():
    contracts = load_gala_contracts()
    url = "https://www.sima-land.ru/950449/kolco/"
    expected = contracts.store_for_url(url)["inn"]
    assert seller_inn_for(url) == expected
