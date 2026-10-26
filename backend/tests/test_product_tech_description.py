"""Тесты build_tech_description (backend/app/services/product_tech_description.py)."""
from app.services.product_tech_description import build_tech_description


def test_only_characteristics():
    result = build_tech_description(
        characteristics=[
            {"name": "Высота", "value": "0.015", "unit": "м"},
            {"name": "Цвет", "value": "Белый"},
        ],
    )
    assert result == "Высота: 0.015 м\nЦвет: Белый"


def test_only_base_text():
    result = build_tech_description(base_text="Просто описание поставщика.")
    assert result == "Просто описание поставщика."


def test_base_text_and_characteristics():
    result = build_tech_description(
        characteristics=[{"name": "Серия", "value": "Mosaic"}],
        base_text="Накладка для розетки.",
    )
    assert result == "Накладка для розетки.\n\nСерия: Mosaic"


def test_empty_input_returns_none():
    assert build_tech_description() is None
    assert build_tech_description(characteristics=[], base_text=None) is None
    assert build_tech_description(characteristics=[], base_text="   ") is None


def test_skips_empty_characteristics():
    result = build_tech_description(
        characteristics=[
            {"name": "Серия", "value": "Mosaic"},
            {"name": "", "value": "без имени"},
            {"name": "Цвет", "value": ""},
            {"name": "Вес", "value": None},
            {},
        ],
    )
    assert result == "Серия: Mosaic"


def test_br_tags_in_base_text_become_newlines():
    result = build_tech_description(base_text="Строка 1<br>Строка 2<br/>Строка 3<br />Строка 4")
    assert result == "Строка 1\nСтрока 2\nСтрока 3\nСтрока 4"


def test_unit_absent_not_appended():
    result = build_tech_description(characteristics=[{"name": "Производитель", "value": "Legrand"}])
    assert result == "Производитель: Legrand"


def test_unit_present_appended_with_space():
    result = build_tech_description(characteristics=[{"name": "Вес", "value": "0.015", "unit": "кг"}])
    assert result == "Вес: 0.015 кг"


def test_none_characteristics_list_treated_as_empty():
    assert build_tech_description(characteristics=None, base_text=None) is None


def test_in_description_false_skipped():
    """Задача 2 (26.10) — характеристики упаковки поставщика
    (in_description=False) не попадают в собранное техописание."""
    result = build_tech_description(
        characteristics=[
            {"name": "Номер по прайс-листу", "value": "123", "in_description": False},
            {"name": "Серия", "value": "Mosaic"},
        ],
    )
    assert result == "Серия: Mosaic"


def test_in_description_absent_or_true_kept():
    result = build_tech_description(
        characteristics=[
            {"name": "Вес", "value": "0.5", "unit": "кг", "in_description": True},
            {"name": "Цвет", "value": "Белый"},
        ],
    )
    assert result == "Вес: 0.5 кг\nЦвет: Белый"
