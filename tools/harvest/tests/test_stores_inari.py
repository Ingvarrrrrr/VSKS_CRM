"""inari.pro — Angular CSR-приложение, сервер не отдаёт данные товара в
статическом HTML (см. докстринг stores/inari.py, "нужна доработка").
Тест фиксирует ЧЕСТНОЕ поведение: разбор живой фикстуры без данных даёт
пустой список, а не выдуманные товары."""
from pathlib import Path

from tools.harvest.core.gala_contracts import load_gala_contracts
from tools.harvest.core.gala_writer import seller_inn_for
from tools.harvest.stores import inari

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_category_page_returns_empty_not_fabricated():
    html = _read("inari_category.html")
    candidates = inari.parse_category_page(html)
    assert candidates == []


def test_needs_product_visit_false_no_candidates_to_enrich():
    assert inari.needs_product_visit({}) is False


def test_build_item_returns_none_without_real_data():
    assert inari.build_item({}, {}, set()) is None


def test_seller_inn_is_none_unconfirmed_requisites():
    # Владелец 27.10.2026: ИНН из старого файла (1832034960) не проходит
    # контрольную цифру — inari.pro сознательно НЕ в справочнике
    # stores.py, seller_inn_for() должен вернуть None, а не выдуманный ИНН.
    contracts = load_gala_contracts()
    url = "https://inari.pro/catalog/products/flagshtoki-parus/483"
    assert contracts.store_for_url(url) is None or contracts.store_for_url(url).get("inn") is None
    assert seller_inn_for(url) is None
