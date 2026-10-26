"""Фолбэк «ТЗ позиции из характеристик каталога» (владелец, 26.10.2026,
жалоба «в заявке не вижу ТЗ»): у товара пустой Product.description, но
заполнены Product.characteristics — effective_item_tz должен собрать текст
из характеристик, а не отдавать пусто.

Единственный источник сборки — app/services/product_tech_description.py::
build_tech_description (ПРАВИЛО №6) — effective_item_tz обязан вызывать
именно его, не собирать текст заново (см. app/services/item_tz.py::
_catalog_fallback). Эти тесты — unit-level (SimpleNamespace), без БД, как и
остальные тесты effective_item_tz в test_item_tz_description.py.
"""
from types import SimpleNamespace

from app.services.item_tz import effective_item_tz, effective_item_tz_44fz


def test_falls_back_to_characteristics_when_description_empty():
    product = SimpleNamespace(
        description=None,
        characteristics=[
            {"name": "Мощность", "value": "3.5", "unit": "кВт"},
            {"name": "Марка", "value": "Husqvarna"},
        ],
    )
    item = SimpleNamespace(tz_description=None, product=product)
    result = effective_item_tz(item)
    assert result == "Мощность: 3.5 кВт\nМарка: Husqvarna"


def test_characteristic_in_description_false_is_excluded_from_fallback():
    product = SimpleNamespace(
        description=None,
        characteristics=[
            {"name": "Мощность", "value": "3.5", "unit": "кВт"},
            {"name": "Номер по прайс-листу", "value": "ABC-123", "in_description": False},
        ],
    )
    item = SimpleNamespace(tz_description=None, product=product)
    result = effective_item_tz(item)
    assert result == "Мощность: 3.5 кВт"
    assert "ABC-123" not in result


def test_own_text_still_wins_over_characteristics_fallback():
    product = SimpleNamespace(
        description=None,
        characteristics=[{"name": "Мощность", "value": "3.5", "unit": "кВт"}],
    )
    item = SimpleNamespace(tz_description="Своё ТЗ позиции", product=product)
    assert effective_item_tz(item) == "Своё ТЗ позиции"


def test_direct_description_wins_over_characteristics_fallback():
    product = SimpleNamespace(
        description="Каталожный текст",
        characteristics=[{"name": "Мощность", "value": "3.5", "unit": "кВт"}],
    )
    item = SimpleNamespace(tz_description=None, product=product)
    assert effective_item_tz(item) == "Каталожный текст"


def test_empty_description_and_no_characteristics_is_none():
    product = SimpleNamespace(description=None, characteristics=None)
    item = SimpleNamespace(tz_description=None, product=product)
    assert effective_item_tz(item) is None


def test_product_without_characteristics_attr_falls_back_safely():
    """Товар (например, старый объект без поля) без атрибута characteristics
    вовсе — getattr с default=None, не падает."""
    product = SimpleNamespace(description=None)
    item = SimpleNamespace(tz_description=None, product=product)
    assert effective_item_tz(item) is None


def test_44fz_also_falls_back_to_characteristics():
    product = SimpleNamespace(
        description_44fz=None,
        characteristics=[{"name": "Марка", "value": "Husqvarna"}],
    )
    item = SimpleNamespace(tz_description=None, product=product)
    assert effective_item_tz_44fz(item) == "Марка: Husqvarna"
