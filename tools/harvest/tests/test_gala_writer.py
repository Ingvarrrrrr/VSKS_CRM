"""Тесты resolve_manufacturer() — без живых запросов, без БД."""
from tools.harvest.core.gala_writer import resolve_manufacturer


def test_brand_from_jsonld_string():
    result = resolve_manufacturer("Дрель MAKITA DP4010", "MAKITA", [], set())
    assert result == "MAKITA"


def test_brand_from_jsonld_object():
    result = resolve_manufacturer(
        "Оперативная память Netac Shadow III",
        {"@type": "Brand", "name": "Netac"},
        [],
        set(),
    )
    assert result == "Netac"


def test_brand_from_characteristic_when_no_jsonld():
    characteristics = [{"name": "Производитель", "value": "Kingston"}]
    result = resolve_manufacturer("Память Kingston Fury", None, characteristics, set())
    assert result == "Kingston"


def test_placeholder_label_never_becomes_manufacturer():
    characteristics = [{"name": "Производитель", "value": "Производитель"}]
    result = resolve_manufacturer("Дрель электрическая", None, characteristics, set())
    assert result is None


def test_parameter_n_characteristic_is_not_a_brand_source():
    characteristics = [{"name": "Параметр 1", "value": "MAKITA"}]
    result = resolve_manufacturer("Дрель электрическая MAKITA", None, characteristics, set())
    # "Параметр 1" не в списке признаваемых имён характеристики бренда —
    # но "MAKITA" всё равно найдётся по словарю известных брендов (seed),
    # это ожидаемо (латиница в начале названия — настоящий бренд).
    assert result == "makita"


def test_leading_category_word_never_becomes_manufacturer():
    # "Лестница" — первое слово названия, тип товара, не бренд (брак
    # старого kuvalda-сборщика: manufacturer = первое слово).
    result = resolve_manufacturer("Лестница алюминиевая раздвижная", None, [], set())
    assert result is None


def test_known_brand_matched_as_separate_word_in_name():
    result = resolve_manufacturer("Процессор Intel Core i5-12400F", None, [], {"intel"})
    assert result == "intel"


def test_country_name_never_becomes_manufacturer():
    result = resolve_manufacturer("Какой-то товар", "Россия", [], set())
    assert result is None
