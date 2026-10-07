"""Задача владельца, п. С4 (30.09.2026):
  - перевозка автобусом не должна позволять «отправление позже окончания»;
  - новые формы «Авиабилеты»/«Железнодорожные билеты» — сумма и описание в ТЗ.

Проверяем ЕДИНУЮ функцию дат (app.services.item_form_dates.validate_item_form_dates,
вызывается из apply_item_amounts — единственная точка сохранения позиции,
см. её докстринг) и формулы/описание flight/train (item_amounts.py/
item_form_summary.py)."""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.item_amounts import apply_item_amounts, compute_item_total
from app.services.item_form_dates import validate_item_form_dates
from app.services.item_form_summary import item_form_summary


# ---------------------------------------------------------------------------
# Даты — transport
# ---------------------------------------------------------------------------

def test_transport_depart_after_finish_rejected():
    item = SimpleNamespace(extra_attrs={
        "depart_at": "2026-10-15T08:00",
        "finish_at": "2026-10-12T08:00",
    })
    with pytest.raises(HTTPException) as exc:
        validate_item_form_dates(item, "transport")
    assert exc.value.status_code == 422
    assert "позже" in exc.value.detail


def test_transport_depart_before_finish_ok():
    item = SimpleNamespace(extra_attrs={
        "depart_at": "2026-10-12T08:00",
        "finish_at": "2026-10-15T08:00",
    })
    validate_item_form_dates(item, "transport")  # no raise


def test_transport_missing_dates_not_validated():
    item = SimpleNamespace(extra_attrs={"depart_at": None, "finish_at": None})
    validate_item_form_dates(item, "transport")  # no raise, nothing to compare


def test_apply_item_amounts_rejects_bad_transport_dates():
    """Та же проверка срабатывает через единственную точку сохранения —
    apply_item_amounts (вызывается и из purchases.py, и из wishes.py)."""
    item = SimpleNamespace(extra_attrs={
        "depart_at": "2026-10-15T08:00",
        "finish_at": "2026-10-12T08:00",
        "work_hours": 5, "hourly_rate": 1000,
    }, item_type=None, quantity=None, unit_price=None, total_price=None)
    with pytest.raises(HTTPException) as exc:
        apply_item_amounts(item, "transport")
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# Даты — flight/train
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("item_form", ["flight", "train"])
def test_return_before_departure_rejected(item_form):
    item = SimpleNamespace(extra_attrs={"date_to": "2026-10-15", "date_back": "2026-10-12"})
    with pytest.raises(HTTPException) as exc:
        validate_item_form_dates(item, item_form)
    assert exc.value.status_code == 422
    assert "раньше" in exc.value.detail


@pytest.mark.parametrize("item_form", ["flight", "train"])
def test_return_after_departure_ok(item_form):
    item = SimpleNamespace(extra_attrs={"date_to": "2026-10-12", "date_back": "2026-10-15"})
    validate_item_form_dates(item, item_form)  # no raise


@pytest.mark.parametrize("item_form", ["flight", "train"])
def test_one_way_without_return_date_ok(item_form):
    item = SimpleNamespace(extra_attrs={"date_to": "2026-10-12", "date_back": None})
    validate_item_form_dates(item, item_form)  # no raise — нет обратной даты, нечего сравнивать


# ---------------------------------------------------------------------------
# Сумма — flight/train
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("item_form", ["flight", "train"])
def test_round_trip_price_not_doubled_by_default(item_form):
    """price_basis по умолчанию 'round_trip' — цена уже введена как полная за
    обе стороны, итог = пассажиров × цена (без ×2)."""
    item = SimpleNamespace(unit_price=None, extra_attrs={
        "passengers": 5, "ticket_price": "12000", "date_to": "2026-10-12", "date_back": "2026-10-15",
    })
    assert compute_item_total(item, item_form) == Decimal("60000.00")


@pytest.mark.parametrize("item_form", ["flight", "train"])
def test_one_way_price_doubled_when_return_date_present(item_form):
    """price_basis='one_way' И есть дата обратно → итог × 2 (цена за один конец)."""
    item = SimpleNamespace(unit_price=None, extra_attrs={
        "passengers": 5, "ticket_price": "12000", "price_basis": "one_way",
        "date_to": "2026-10-12", "date_back": "2026-10-15",
    })
    assert compute_item_total(item, item_form) == Decimal("120000.00")


@pytest.mark.parametrize("item_form", ["flight", "train"])
def test_one_way_price_not_doubled_without_return_trip(item_form):
    """price_basis='one_way', но обратной даты нет (поездка в одну сторону) —
    без ×2."""
    item = SimpleNamespace(unit_price=None, extra_attrs={
        "passengers": 5, "ticket_price": "12000", "price_basis": "one_way",
        "date_to": "2026-10-12", "date_back": None,
    })
    assert compute_item_total(item, item_form) == Decimal("60000.00")


@pytest.mark.parametrize("item_form", ["flight", "train"])
def test_apply_item_amounts_sets_quantity_and_unit_price(item_form):
    item = SimpleNamespace(
        unit_price=None, quantity=None, total_price=None, item_type=None,
        extra_attrs={
            "passengers": 5, "ticket_price": "12000", "price_basis": "one_way",
            "date_to": "2026-10-12", "date_back": "2026-10-15",
        },
    )
    total = apply_item_amounts(item, item_form)
    assert item.item_type == "услуга"
    assert item.quantity == Decimal("10")  # 5 пассажиров × 2 (один конец + обратно)
    assert item.unit_price == Decimal("12000")
    assert total == Decimal("120000.00")


# ---------------------------------------------------------------------------
# Описание в ТЗ — item_form_summary (С5: тот же построитель, что у
# питания/проживания/перевозки)
# ---------------------------------------------------------------------------

def test_flight_summary_text():
    item = SimpleNamespace(extra_attrs={
        "place_from": "Москва", "place_to": "Сочи",
        "date_to": "2026-10-12", "date_back": "2026-10-15",
        "passengers": 5, "fare_class": "economy", "ticket_price": "12000",
    })
    summary = item_form_summary(item, "flight")
    assert summary == "Москва — Сочи, 2026-10-12–2026-10-15, 5 пасс., Эконом, × 12 000,00 ₽"


def test_train_summary_text():
    item = SimpleNamespace(extra_attrs={
        "place_from": "Москва", "place_to": "Курск",
        "date_to": "2026-10-12", "date_back": None,
        "passengers": 2, "fare_class": "kupe", "ticket_price": "3500",
    })
    summary = item_form_summary(item, "train")
    assert summary == "Москва — Курск, 2026-10-12, 2 пасс., Купе, × 3 500,00 ₽"
