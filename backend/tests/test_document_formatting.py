# -*- coding: utf-8 -*-
"""Форматирование количества для документов (ТЗ/договор/поставка).

Владелец (2026-09-17): «количество должно передаваться как целое число, 32,
а не 32.0» — items_list раньше клал "quantity": float(qty), а docxtpl печатал
Python-репрезентацию float целиком. Единственная функция форматирования —
app.services.documents.formatting._fmt_quantity — используется во ВСЕХ
builders items_list (contexts.py, fabrikant_package.py, wish_documents.py),
проверяем её саму, без БД и шаблонов.
"""
from decimal import Decimal

from app.services.documents.formatting import _fmt_quantity


def test_whole_number_float_has_no_trailing_dot_zero():
    assert _fmt_quantity(32.0) == "32"
    assert _fmt_quantity(1.0) == "1"
    assert _fmt_quantity(0.0) == "0"


def test_whole_number_int_unchanged():
    assert _fmt_quantity(32) == "32"


def test_whole_number_decimal_from_db_has_no_trailing_zero():
    # SQLAlchemy Numeric-колонки (purchase_items.quantity и т.п.) приходят
    # как Decimal — именно так качество попадает в items_list в реальности.
    assert _fmt_quantity(Decimal("32.0000")) == "32"
    assert _fmt_quantity(Decimal("1.00")) == "1"


def test_fractional_quantity_keeps_meaningful_decimals_with_comma():
    assert _fmt_quantity(32.5) == "32,5"
    assert _fmt_quantity(Decimal("32.50")) == "32,5"
    assert _fmt_quantity(0.25) == "0,25"


def test_empty_and_none_render_as_empty_string():
    assert _fmt_quantity(None) == ""
    assert _fmt_quantity("") == ""


def test_non_numeric_value_falls_back_to_str():
    assert _fmt_quantity("шт.") == "шт."
