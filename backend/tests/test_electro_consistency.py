"""Тесты backend/app/services/catalog_gala/electro_consistency.py — владелец,
2026-10-26: кабели, где «N×S» в названии противоречит характеристикам
«Сечение жилы кабеля»/«Количество жил кабеля», не загружаются в каталог."""
from app.services.catalog_gala.electro_consistency import check_cable_consistency


def test_section_mismatch_excluded():
    ok, reason = check_cable_consistency(
        "Провод ПуВ 1х2,5 кв.мм белый",
        [{"name": "Сечение жилы кабеля", "value": "1.5", "unit": "мм²"}],
    )
    assert ok is False
    assert "сечение" in reason.lower()


def test_count_mismatch_excluded():
    ok, reason = check_cable_consistency(
        "Кабель ВВГ 3х1,5 кв.мм",
        [
            {"name": "Сечение жилы кабеля", "value": "1.5", "unit": "мм²"},
            {"name": "Количество жил кабеля", "value": "2", "unit": None},
        ],
    )
    assert ok is False
    assert "жил" in reason.lower()


def test_matching_values_not_excluded():
    ok, reason = check_cable_consistency(
        "Кабель ВВГ 3х1,5 кв.мм",
        [
            {"name": "Сечение жилы кабеля", "value": "1.5", "unit": "мм²"},
            {"name": "Количество жил кабеля", "value": "3", "unit": None},
        ],
    )
    assert ok is True
    assert reason is None


def test_triple_pair_formula_only_section_compared():
    """«1х2х1,5» (пара жил) — сравнивается только последнее число (сечение),
    количество жил НЕ сравнивается (формула неоднозначна)."""
    ok, reason = check_cable_consistency(
        "Провод ПуГВ 1х2х1,5",
        [
            {"name": "Сечение жилы кабеля", "value": "1.5", "unit": "мм²"},
            {"name": "Количество жил кабеля", "value": "99", "unit": None},  # не сравнивается
        ],
    )
    assert ok is True


def test_triple_pair_formula_section_mismatch_still_excluded():
    ok, reason = check_cable_consistency(
        "Провод ПуГВ 1х2х1,5",
        [{"name": "Сечение жилы кабеля", "value": "4.0", "unit": "мм²"}],
    )
    assert ok is False


def test_no_nxs_pattern_not_excluded():
    ok, reason = check_cable_consistency(
        "Выключатель одноклавишный Mosaic",
        [{"name": "Сечение жилы кабеля", "value": "999", "unit": "мм²"}],
    )
    assert ok is True
    assert reason is None


def test_missing_characteristic_not_excluded():
    ok, reason = check_cable_consistency("Кабель ВВГ 3х1,5 кв.мм", [])
    assert ok is True


def test_non_numeric_count_characteristic_skipped():
    """"Количество жил кабеля" не чисто числовое → сравнение пропускается."""
    ok, reason = check_cable_consistency(
        "Кабель ВВГ 3х1,5 кв.мм",
        [
            {"name": "Сечение жилы кабеля", "value": "1.5", "unit": "мм²"},
            {"name": "Количество жил кабеля", "value": "3 жилы", "unit": None},
        ],
    )
    assert ok is True


def test_empty_name_not_excluded():
    assert check_cable_consistency(None, [{"name": "Сечение жилы кабеля", "value": "1"}]) == (True, None)
    assert check_cable_consistency("", []) == (True, None)
