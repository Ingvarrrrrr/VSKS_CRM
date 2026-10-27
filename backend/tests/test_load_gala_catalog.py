"""Тесты scripts/load_gala_catalog.py — item_to_row (владелец, 27.10.2026):
manufacturer-«брак» не передаётся в строку импорта (is_bogus_manufacturer,
catalog_gala.manufacturer_quality), seller_inn разрешается по
catalog_gala.stores.resolve_seller_inn (домен товарной ссылки побеждает
значение файла; неизвестный домен — только с верной контрольной цифрой)."""
from scripts.load_gala_catalog import COL_IDX, item_to_row


def _base_item(**overrides):
    item = {
        "name": "Лестница алюминиевая раздвижная",
        "manufacturer": "Лестница",
        "manufacturer_article": "LA-123",
        "seller_inn": None,
        "links": [],
        "source_url": None,
    }
    item.update(overrides)
    return item


def test_bogus_manufacturer_not_written_to_row():
    item = _base_item()
    row = item_to_row(item)
    assert row[COL_IDX["manufacturer"]] is None


def test_real_manufacturer_written_to_row():
    item = _base_item(name="Дрель безударная сетевая MAKITA M0600", manufacturer="MAKITA")
    row = item_to_row(item)
    assert row[COL_IDX["manufacturer"]] == "MAKITA"


def test_seller_inn_replaced_by_known_store_domain():
    item = _base_item(seller_inn="7722395663", links=[{"url": "https://kns.ru/p/1"}])
    row = item_to_row(item)
    assert row[COL_IDX["seller_inn"]] == "9723033526"


def test_seller_inn_invalid_and_unknown_domain_becomes_none():
    item = _base_item(seller_inn="1832034960", links=[{"url": "https://inari.pro/p/1"}])
    row = item_to_row(item)
    assert row[COL_IDX["seller_inn"]] is None


def test_seller_inn_falls_back_to_source_url_when_no_links():
    item = _base_item(seller_inn=None, links=[], source_url="https://kuvalda.ru/p/1")
    row = item_to_row(item)
    assert row[COL_IDX["seller_inn"]] == "6319060894"
