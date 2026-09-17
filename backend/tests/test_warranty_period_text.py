"""Независимая приёмка (2026-09-17, п.7): покрытие warranty_period_text().

Владелец (п.10): «Срок гарантии может быть в днях, в месяцах, в годах ... В
документ должно уходить то, что выбрано словами, а не пересчёт в дни.»
warranty_period_text() (app/services/documents/contract_terms.py) — ЕДИНСТВЕННОЕ
место, где считается склонение (ПРАВИЛО №6). Тест закрепляет:
  - правильное русское склонение по числу (1/2/5, включая 11-14 → «много»);
  - unit=None трактуется как 'days' (совместимость со старыми закупками,
    заведёнными до появления warranty_period_unit);
  - value=None → пустая строка (гарантия не задана) при ЛЮБОМ unit.
"""
import pytest

from app.services.documents.contract_terms import warranty_period_text


@pytest.mark.parametrize(
    "value, unit, expected",
    [
        # (15, None) — старая закупка без unit трактуется как 'days'.
        (15, None, "15 дней"),
        (1, "years", "1 год"),
        (2, "years", "2 года"),
        (5, "years", "5 лет"),
        (1, "months", "1 месяц"),
        (3, "months", "3 месяца"),
        (12, "months", "12 месяцев"),
        (1, "days", "1 день"),
        (3, "days", "3 дня"),
        (30, "days", "30 дней"),
    ],
)
def test_warranty_period_text_declension(value, unit, expected):
    assert warranty_period_text(value, unit) == expected


@pytest.mark.parametrize("unit", [None, "days", "months", "years"])
def test_warranty_period_text_zero_uses_many_form(unit):
    # 0 попадает в форму «много» (0 % 10 == 0, не 1 и не 2..4).
    result = warranty_period_text(0, unit)
    assert result.startswith("0 ")
    assert result in ("0 дней", "0 месяцев", "0 лет")


@pytest.mark.parametrize("unit", [None, "days", "months", "years", "bogus_unit"])
def test_warranty_period_text_none_value_is_empty_regardless_of_unit(unit):
    # Гарантия не задана — пустая строка независимо от unit (даже мусорного).
    assert warranty_period_text(None, unit) == ""


def test_warranty_period_text_unknown_unit_falls_back_to_days():
    # Неизвестная единица (защита от опечатки в данных) — тоже трактуется как 'days'.
    assert warranty_period_text(11, "bogus_unit") == "11 дней"


@pytest.mark.parametrize(
    "value, unit, expected",
    [
        (11, "years", "11 лет"),
        (12, "years", "12 лет"),
        (13, "years", "13 лет"),
        (14, "years", "14 лет"),
        (21, "years", "21 год"),
        (22, "years", "22 года"),
        (25, "years", "25 лет"),
    ],
)
def test_warranty_period_text_teens_exception(value, unit, expected):
    # 11-14 (и 111-114 и т.п.) — всегда «много», даже когда последняя цифра 1-4.
    assert warranty_period_text(value, unit) == expected
