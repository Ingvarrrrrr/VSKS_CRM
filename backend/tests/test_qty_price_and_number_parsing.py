"""Дефект 1+2 (владелец, 2026-09-14): разбор чисел с точкой-разделителем
тысяч и проверка «количество × цена = сумма» при импорте позиций закупки.

Причина боевого дефекта — позиция закупки id=3166 «Ретранслятор TYT MD 7500
UHF», 5 шт по 99 990: код заменял запятую на точку ДО разбора числа, поэтому
"499.950,00" превращался в "499.950.00", откуда бралось только "499.950" →
Decimal("499.95") вместо верных 499950. Единственный источник разбора теперь
`app.utils.numbers.to_decimal` (Правило №6) — раньше в каждом импортёре была
своя копия-регулярка (`purchase_items_import_mapped.py` — ДВЕ копии).

Проверка кол-во × цена = сумма — `app.services.qty_price_check` (тот же
допуск и текст, что у импорта ФЭО, `feo_import_apply.py`, kind=sum_mismatch).

Чистые unit-тесты, БД не нужна — гонять можно как угодно, но для единообразия
с остальными тестами импорта см. project_pytest_asyncio_loop_flake (по
одному узлу за вызов pytest в контейнере).
"""
from decimal import Decimal

import pytest

from app.utils.numbers import to_decimal, to_decimal_ambiguous
from app.services.qty_price_check import check_qty_price_sum, resolve_qty_price_choice


# ── Дефект 1: разбор чисел ───────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("499.950,00", Decimal("499950.00")),      # точка-тысячи + запятая-дробь
    ("1.234.567,89", Decimal("1234567.89")),   # несколько точек-тысяч
    ("99.990,00", Decimal("99990.00")),        # тот самый боевой случай (id=3166)
    ("499 950,00", Decimal("499950.00")),      # пробел-тысячи (уже работало)
    ("499,95", Decimal("499.95")),             # обычная запятая-дробь (уже работало)
])
def test_to_decimal_thousand_separator_formats(raw, expected):
    assert to_decimal(raw) == expected


def test_to_decimal_single_dot_three_digits_is_ambiguous_but_resolved_as_thousands():
    """"1.500" — неоднозначно (может быть 1500 или 1.5). В русских выгрузках
    почти всегда тысячи, поэтому разбираем как 1500, но помечаем ambiguous=True,
    чтобы вызывающий код (предпросмотр импорта) мог предупредить пользователя."""
    value, ambiguous = to_decimal_ambiguous("1.500")
    assert value == Decimal("1500")
    assert ambiguous is True


@pytest.mark.parametrize("raw, expected", [
    ("499.95", Decimal("499.95")),   # 2 цифры после точки — обычная дробь, не тысячи
    ("1.5", Decimal("1.5")),         # 1 цифра — обычная дробь
])
def test_to_decimal_single_dot_not_three_digits_is_not_ambiguous(raw, expected):
    value, ambiguous = to_decimal_ambiguous(raw)
    assert value == expected
    assert ambiguous is False


def test_to_decimal_none_and_empty():
    assert to_decimal(None) is None
    assert to_decimal("-") is None
    assert to_decimal("") is None


def test_to_decimal_plain_numeric_types_unaffected():
    assert to_decimal(99990) == Decimal("99990")
    assert to_decimal(99990.5) == Decimal("99990.5")


# ── Дефект 2: проверка кол-во × цена = сумма ─────────────────────────────────

def test_matching_row_is_silent():
    """5 шт по 99 990 = 499 950 — произведение сходится, предупреждения нет."""
    assert check_qty_price_sum(7, "Ретранслятор", Decimal("5"), Decimal("99990"), Decimal("499950")) is None


def test_thousandfold_mismatch_warns_with_row_number():
    """Боевой случай: сумма в файле — 499.95 вместо 499 950 (расхождение в
    1000 раз). Предупреждение обязано назвать номер строки файла."""
    w = check_qty_price_sum(7, "Ретранслятор TYT MD 7500 UHF", Decimal("5"), Decimal("99990"), Decimal("499.95"))
    assert w is not None
    assert w["kind"] == "sum_mismatch"
    assert w["row"] == 7
    assert w["name"] == "Ретранслятор TYT MD 7500 UHF"
    assert w["calc_total"] == 499950.0
    assert w["file_total"] == 499.95


def test_kopek_rounding_difference_is_silent():
    """Расхождение ровно на копейку (в пределах допуска) — тишина, не ложное
    предупреждение: 3 × 10 = 30.00, в файле 30.01."""
    assert check_qty_price_sum(1, "X", Decimal("3"), Decimal("10"), Decimal("30.01")) is None


@pytest.mark.parametrize("quantity, unit_price, total_price", [
    (None, Decimal("100"), Decimal("500")),
    (Decimal("5"), None, Decimal("500")),
    (Decimal("5"), Decimal("100"), None),
    (None, None, None),
])
def test_missing_any_of_three_fields_is_silent(quantity, unit_price, total_price):
    """Если не заполнены ВСЕ три поля (кол-во, цена, сумма) — тишина: это не
    дефект строки, а просто «поле не заполнено в файле»."""
    assert check_qty_price_sum(1, "X", quantity, unit_price, total_price) is None


def test_resolve_choice_recalc_sum_gives_quantity_times_price():
    unit_price, total_price = resolve_qty_price_choice(Decimal("5"), Decimal("99990"), Decimal("499.95"), "recalc_sum")
    assert unit_price == Decimal("99990")
    assert total_price == Decimal("499950.00")


def test_resolve_choice_recalc_price_gives_sum_over_quantity():
    unit_price, total_price = resolve_qty_price_choice(Decimal("5"), Decimal("99990"), Decimal("499950"), "recalc_price")
    assert unit_price == Decimal("99990.00")
    assert total_price == Decimal("499950")  # сумма не трогается


def test_resolve_choice_keep_changes_nothing():
    unit_price, total_price = resolve_qty_price_choice(Decimal("5"), Decimal("99990"), Decimal("499.95"), "keep")
    assert unit_price == Decimal("99990")
    assert total_price == Decimal("499.95")


def test_resolve_choice_none_changes_nothing():
    unit_price, total_price = resolve_qty_price_choice(Decimal("5"), Decimal("99990"), Decimal("499.95"), None)
    assert unit_price == Decimal("99990")
    assert total_price == Decimal("499.95")
