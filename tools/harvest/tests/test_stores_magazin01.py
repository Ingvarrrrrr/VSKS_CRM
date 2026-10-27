"""Парсинг СИНТЕТИЧЕСКИХ fixture-страниц magazin01.ru (живые запросы к
этому магазину запрещены в рамках задания — см. докстринг
stores/magazin01.py, "нужна доработка")."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import seller_inn_for
from tools.harvest.stores import magazin01

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_sitemap_filters_products():
    xml_text = _read("magazin01_sitemap.xml")
    candidates = magazin01.parse_category_page(xml_text)
    assert len(candidates) == 2
    assert all("/product/" in c["url"] for c in candidates)


def test_category_always_needs_product_visit():
    xml_text = _read("magazin01_sitemap.xml")
    candidates = magazin01.parse_category_page(xml_text)
    assert all(magazin01.needs_product_visit(c) for c in candidates)


def test_parse_product_page_brand_and_store_article_from_jsonld():
    html = _read("magazin01_product_1.html")
    enrichment = magazin01.parse_product_page(html, "https://magazin01.ru/product/x/")
    assert enrichment["name"]
    assert enrichment["jsonld_brand"] is None  # JSON-LD в фикстуре без brand — не придумываем
    assert enrichment["store_article"] == "4601234567890"
    assert len(enrichment["characteristics"]) > 0


def test_no_placeholder_characteristic_names():
    for fixture in ("magazin01_product_1.html", "magazin01_product_2.html"):
        html = _read(fixture)
        enrichment = magazin01.parse_product_page(html, "https://magazin01.ru/product/x/")
        for c in enrichment["characteristics"]:
            assert not c["name"].strip().lower().startswith("параметр")


def test_build_item_manufacturer_article_never_fabricated():
    html = _read("magazin01_product_1.html")
    enrichment = magazin01.parse_product_page(html, "https://magazin01.ru/product/x/")
    item = magazin01.build_item({"url": "https://magazin01.ru/product/x/"}, enrichment, set())
    assert item["manufacturer_article"] is None
    assert item["store_article"] == "4601234567890"


def test_seller_inn_matches_stores_dictionary():
    contracts = load_gala_contracts()
    url = "https://magazin01.ru/product/x/"
    expected = contracts.store_for_url(url)["inn"]
    assert seller_inn_for(url) == expected
