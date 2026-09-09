"""item-forms-accommodation-transport.md, шаг 1: формулы compute_item_total/
apply_item_amounts (app/services/item_amounts.py) — единственный писатель
total_price для позиций со спец-формой («Проживание»/«Перевозки автобусом»,
см. app/services/item_forms.py) и для обычной формы (line_total).

Числа владельца («Корректировки GALA 7 сентября»): 6600 × 8 номеров × 1 сутки
= 52800 — контрольный пример, на котором сходится формула «за номер».
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.item_amounts import compute_item_total, apply_item_amounts, line_total


def _item(**kwargs):
    """Лёгкий объект с атрибутами item-подобного объекта (quantity/unit_price/
    extra_attrs) — apply_item_amounts/compute_item_total работают через getattr,
    им всё равно, ORM это или SimpleNamespace."""
    defaults = {"quantity": None, "unit_price": None, "extra_attrs": {}, "total_price": None}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_line_total_plain_multiplication():
    assert line_total(Decimal("3"), Decimal("150.5")) == Decimal("451.50")


def test_ordinary_form_unchanged_by_apply_item_amounts():
    """item_form=None — обычная позиция, поведение НЕ меняется (qty × price)."""
    it = _item(quantity=Decimal("4"), unit_price=Decimal("250"))
    total = apply_item_amounts(it, None)
    assert total == Decimal("1000.00")
    assert it.total_price == Decimal("1000.00")
    assert it.quantity == Decimal("4")  # не тронуто
    assert it.unit_price == Decimal("250")  # не тронуто


def test_accommodation_by_room_owner_example():
    """Владелец: 6600 × 8 номеров × 1 сутки = 52800."""
    it = _item(
        unit_price=Decimal("6600"),
        extra_attrs={"price_basis": "room", "rooms": 8, "persons": 0, "nights": 1},
    )
    total = apply_item_amounts(it, "accommodation")
    assert total == Decimal("52800.00")
    assert it.total_price == Decimal("52800.00")
    assert it.quantity == Decimal("8")  # производная величина — заведена из rooms


def test_accommodation_by_person():
    """6600 × 32 человека × 1 сутки = 211200 — переключатель «за человека»."""
    it = _item(
        unit_price=Decimal("6600"),
        extra_attrs={"price_basis": "person", "rooms": 8, "persons": 32, "nights": 1},
    )
    total = apply_item_amounts(it, "accommodation")
    assert total == Decimal("211200.00")
    assert it.quantity == Decimal("32")


def test_accommodation_nights_multiplier():
    """Суток = 3, база — номера: 6600 × 8 × 3 = 158400."""
    it = _item(
        unit_price=Decimal("6600"),
        extra_attrs={"price_basis": "room", "rooms": 8, "nights": 3},
    )
    total = apply_item_amounts(it, "accommodation")
    assert total == Decimal("158400.00")


def test_accommodation_nights_default_is_one():
    """nights не задано в extra_attrs → умолчание 1 (план: «по умолчанию 1»)."""
    it = _item(unit_price=Decimal("1000"), extra_attrs={"price_basis": "room", "rooms": 2})
    total = apply_item_amounts(it, "accommodation")
    assert total == Decimal("2000.00")


def test_transport_hours_mode_owner_example():
    """Владелец: 1500 ₽/ч × (5 работы + 2 подачи) = 10500."""
    it = _item(
        extra_attrs={
            "work_hours": 5, "supply_hours": 2, "hourly_rate": 1500, "cost_mode": "hours",
        },
    )
    total = apply_item_amounts(it, "transport")
    assert total == Decimal("10500.00")
    assert it.quantity == Decimal("7")
    assert it.unit_price == Decimal("1500")


def test_transport_supply_hours_defaults_to_two():
    """supply_hours не задано → умолчание 2 (план: «по умолчанию 2, редактируется»)."""
    it = _item(extra_attrs={"work_hours": 5, "hourly_rate": 1000, "cost_mode": "hours"})
    total = apply_item_amounts(it, "transport")
    assert it.quantity == Decimal("7")  # 5 + 2 (умолчание)
    assert total == Decimal("7000.00")


def test_transport_trip_mode_manual_cost():
    """Режим «стоимость рейса вручную»: quantity=1, total = введённая сумма."""
    it = _item(extra_attrs={"cost_mode": "trip", "trip_cost": 12000, "work_hours": 99, "hourly_rate": 999})
    total = apply_item_amounts(it, "transport")
    assert total == Decimal("12000.00")
    assert it.quantity == Decimal("1")
    assert it.unit_price == Decimal("12000")


def test_compute_item_total_does_not_mutate():
    """compute_item_total — превью, НЕ пишет в item (в отличие от apply_item_amounts)."""
    it = _item(unit_price=Decimal("100"), quantity=Decimal("2"), extra_attrs={})
    total = compute_item_total(it, None)
    assert total == Decimal("200.00")
    assert it.total_price is None  # не тронуто — total_price не выставлялся ни разу
