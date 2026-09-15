"""item-forms-accommodation-transport.md, шаг 4: services/item_form_summary.py —
ЕДИНСТВЕННАЯ функция человекочитаемого описания позиции спец-формы (Правило
№6). Проверяем три сценария владельца («номера», «люди», «рейс по часам»,
«рейс фиксированной ценой») и пустую строку для обычной позиции, а также то,
что _build_items_list_from_purchase_items (services/documents/contexts.py,
доступна через app.routers.documents, как в
tests/test_contract_documents_use_contract_items.py) прокидывает extra_attrs
и form_summary в items_list, не трогая рендер docx (юнит, без документа).
"""
from decimal import Decimal
from types import SimpleNamespace

from app.routers import documents as docs
from app.services.item_form_summary import item_form_summary, item_menu_lines


# ---------------------------------------------------------------------------
# item_form_summary — формулы владельца
# ---------------------------------------------------------------------------

def test_accommodation_by_room():
    """«Стандартный четырёхместный, 8 номеров × 6 600,00 ₽ × 3 сут.»"""
    item = SimpleNamespace(
        unit_price=Decimal("6600"),
        extra_attrs={
            "room_category": "Стандартный четырёхместный",
            "price_basis": "room",
            "rooms": 8,
            "persons": 0,
            "nights": 3,
        },
    )
    assert item_form_summary(item, "accommodation") == (
        "Стандартный четырёхместный, 8 номеров × 6 600,00 ₽ × 3 сут."
    )


def test_accommodation_by_person():
    """«... за человека: 32 чел. × 6 600,00 ₽ × 3 сут.» (переключатель price_basis)."""
    item = SimpleNamespace(
        unit_price=Decimal("6600"),
        extra_attrs={"price_basis": "person", "persons": 32, "nights": 3},
    )
    assert item_form_summary(item, "accommodation") == (
        "за человека: 32 чел. × 6 600,00 ₽ × 3 сут."
    )


def test_transport_hours_mode():
    """«Москва → Курск, 32 чел., подача 07.05.2026 08:00, 5 ч работы + 2 ч
    подачи × 1 500,00 ₽/ч» (режим «по часам»)."""
    item = SimpleNamespace(
        extra_attrs={
            "place_from": "Москва",
            "place_to": "Курск",
            "persons": 32,
            "depart_at": "2026-05-07T08:00:00",
            "work_hours": 5,
            "supply_hours": 2,
            "hourly_rate": 1500,
            "cost_mode": "hours",
        },
    )
    assert item_form_summary(item, "transport") == (
        "Москва → Курск, 32 чел., подача 07.05.2026 08:00, "
        "5 ч работы + 2 ч подачи × 1 500,00 ₽/ч"
    )


def test_transport_trip_mode():
    """«... стоимость рейса 12 000,00 ₽» (переключатель cost_mode=trip)."""
    item = SimpleNamespace(
        extra_attrs={
            "place_from": "Москва",
            "place_to": "Курск",
            "persons": 32,
            "depart_at": "2026-05-07T08:00:00",
            "cost_mode": "trip",
            "trip_cost": 12000,
        },
    )
    assert item_form_summary(item, "transport") == (
        "Москва → Курск, 32 чел., подача 07.05.2026 08:00, стоимость рейса 12 000,00 ₽"
    )


def test_food_summary():
    """«10 чел. × 3 приёма/день × 5 дн. × 250,00 ₽» (формула владельца: человек
    × приёмов пищи × дней, цена — за приём)."""
    item = SimpleNamespace(
        unit_price=Decimal("250"),
        extra_attrs={"persons": 10, "meals_per_day": 3, "days": 5},
    )
    assert item_form_summary(item, "food") == (
        "10 чел. × 3 приёма/день × 5 дн. × 250,00 ₽"
    )


def test_food_summary_empty_meals_and_days_default_to_one():
    """Пустые meals_per_day/days — трактуются как 1, ровно как в
    _food_quantity (item_amounts.py), иначе описание разойдётся с суммой."""
    item = SimpleNamespace(
        unit_price=Decimal("250"),
        extra_attrs={"persons": 4, "meals_per_day": "", "days": None},
    )
    assert item_form_summary(item, "food") == (
        "4 чел. × 1 приём/день × 1 дн. × 250,00 ₽"
    )


def test_food_summary_zero_persons_not_empty():
    """persons=0 — описание всё равно строится (не пустая строка)."""
    item = SimpleNamespace(
        unit_price=Decimal("250"),
        extra_attrs={"persons": 0, "meals_per_day": 3, "days": 1},
    )
    assert item_form_summary(item, "food") == (
        "0 чел. × 3 приёма/день × 1 дн. × 250,00 ₽"
    )


_OWNER_MENU = [
    {"day": 1, "meals": [
        {"name": "Завтрак", "description": "каша, чай", "price": 200},
        {"name": "Обед", "description": "суп, второе", "price": 350},
        {"name": "Ужин", "description": "рагу", "price": 300},
    ]},
    {"day": 2, "meals": [
        {"name": "Завтрак", "description": "каша, чай", "price": 200},
        {"name": "Обед", "description": "суп, второе", "price": 350},
        {"name": "Ужин", "description": "рагу", "price": 300},
    ]},
]


def test_food_menu_summary():
    """«10 чел. × 2 дн., 6 приёмов — 1 700,00 ₽ на человека, итого
    17 000,00 ₽» — краткая сводка режима «меню по дням» (владелец, 2026-09-15)."""
    item = SimpleNamespace(extra_attrs={"mode": "menu", "persons": 10, "days": 2, "menu": _OWNER_MENU})
    assert item_form_summary(item, "food") == (
        "10 чел. × 2 дн., 6 приёмов — 1 700,00 ₽ на человека, итого 17 000,00 ₽"
    )


def test_food_menu_lines_full_breakdown():
    """Полная раскладка по дням для ТЗ — одна строка на день, приёмы через «; »,
    состав в скобках после цены."""
    item = SimpleNamespace(extra_attrs={"mode": "menu", "persons": 10, "days": 2, "menu": _OWNER_MENU})
    lines = item_menu_lines(item, "food")
    assert lines == [
        "День 1 — Завтрак (200,00 ₽): каша, чай; Обед (350,00 ₽): суп, второе; Ужин (300,00 ₽): рагу",
        "День 2 — Завтрак (200,00 ₽): каша, чай; Обед (350,00 ₽): суп, второе; Ужин (300,00 ₽): рагу",
    ]


def test_food_menu_lines_empty_for_simple_mode_and_other_forms():
    """menu_lines пуст для food/просто, для accommodation/transport и для
    обычной позиции — не только form_summary, но и полная раскладка."""
    simple_item = SimpleNamespace(extra_attrs={"persons": 10, "meals_per_day": 3, "days": 5})
    assert item_menu_lines(simple_item, "food") == []

    accommodation_item = SimpleNamespace(extra_attrs={"price_basis": "room", "rooms": 1, "nights": 1})
    assert item_menu_lines(accommodation_item, "accommodation") == []

    ordinary_item = SimpleNamespace(extra_attrs={})
    assert item_menu_lines(ordinary_item, None) == []


def test_food_menu_lines_meal_without_description():
    """Приём без состава — печатается без «: …» на конце."""
    item = SimpleNamespace(extra_attrs={
        "mode": "menu", "persons": 1,
        "menu": [{"day": 1, "meals": [{"name": "Перекус", "price": 50}]}],
    })
    assert item_menu_lines(item, "food") == ["День 1 — Перекус (50,00 ₽)"]


def test_ordinary_item_empty_summary():
    """item_form=None (обычная позиция) — пустая строка, не None."""
    item = SimpleNamespace(unit_price=Decimal("100"), extra_attrs={})
    assert item_form_summary(item, None) == ""


def test_unknown_item_form_empty_summary():
    """Неизвестный/будущий код формы — тоже пустая строка, а не исключение."""
    item = SimpleNamespace(extra_attrs={"whatever": 1})
    assert item_form_summary(item, "some_future_form") == ""


# ---------------------------------------------------------------------------
# Интеграция с контекстом документа: _build_items_list_from_purchase_items
# ---------------------------------------------------------------------------

def _mk_purchase_item_with_extra(name, price, extra_attrs, qty=1, unit="шт", item_type="услуга"):
    qty_d = Decimal(str(qty))
    price_d = Decimal(str(price))
    return SimpleNamespace(
        item_name=name,
        item_type=item_type,
        unit=unit,
        unit_price=price_d,
        quantity=qty_d,
        total_price=price_d * qty_d,
        product_id=None,
        product=None,
        country_origin=None,
        vat_rate=None,
        feo_category_id=None,
        feo_planned_item_id=None,
        extra_attrs=extra_attrs,
    )


def test_purchase_items_context_carries_extra_and_form_summary():
    """Позиция закупки с contract_form=services_accommodation и extra_attrs
    даёт непустой item.form_summary и item.extra == extra_attrs в items_list —
    без рендера docx, только построение контекста (как в
    test_contract_documents_use_contract_items.py)."""
    extra_attrs = {
        "room_category": "Стандартный четырёхместный",
        "price_basis": "room",
        "rooms": 8,
        "persons": 0,
        "nights": 3,
    }
    item = _mk_purchase_item_with_extra("Номер стандарт", "6600", extra_attrs)
    p = SimpleNamespace(items=[item], contract_form="services_accommodation")

    items_list = docs._build_items_list_from_purchase_items(p)

    assert len(items_list) == 1
    out = items_list[0]
    assert out["extra"] == extra_attrs
    assert out["form_summary"] == (
        "Стандартный четырёхместный, 8 номеров × 6 600,00 ₽ × 3 сут."
    )


def test_purchase_items_context_ordinary_purchase_has_empty_extra_and_summary():
    """Обычная закупка (contract_form=None) — extra пустой словарь,
    form_summary пустая строка (регресс: обычные документы не видят «мусора»)."""
    item = _mk_purchase_item_with_extra("Обычный товар", "100", {}, item_type="товар")
    p = SimpleNamespace(items=[item], contract_form=None)

    items_list = docs._build_items_list_from_purchase_items(p)

    assert len(items_list) == 1
    out = items_list[0]
    assert out["extra"] == {}
    assert out["form_summary"] == ""


def test_contract_items_context_carries_extra_and_form_summary():
    """Тот же прогон для договорных позиций (_build_items_list_from_contract_items)
    — форма выводится из закупки (contract_form), не из самой ContractItem."""
    extra_attrs = {
        "place_from": "Москва", "place_to": "Курск", "persons": 32,
        "depart_at": "2026-05-07T08:00:00", "cost_mode": "trip", "trip_cost": 12000,
    }
    ci = SimpleNamespace(
        name="Автобус ПАЗ", quantity=Decimal("1"), unit="рейс",
        unit_price=Decimal("12000"), total=Decimal("12000"), product=None,
        extra_attrs=extra_attrs,
    )
    p = SimpleNamespace(contract_items=[ci], contract_form="services_transport")

    items_list = docs._build_items_list_from_contract_items(p)

    assert len(items_list) == 1
    out = items_list[0]
    assert out["extra"] == extra_attrs
    assert out["form_summary"] == (
        "Москва → Курск, 32 чел., подача 07.05.2026 08:00, стоимость рейса 12 000,00 ₽"
    )


def test_purchase_items_context_carries_menu_lines_for_food_menu_mode():
    """food-menu-editor.md: items_list прокидывает menu_lines для food+menu
    и пустой список для обычных позиций (ключ ВСЕГДА присутствует — шаблон
    не должен упасть на неопределённой переменной)."""
    extra_attrs = {"mode": "menu", "persons": 10, "days": 2, "menu": _OWNER_MENU}
    item = _mk_purchase_item_with_extra("Питание группы", "283.33", extra_attrs, qty=60)
    ordinary = _mk_purchase_item_with_extra("Обычный товар", "100", {}, item_type="товар")
    p = SimpleNamespace(items=[item, ordinary], contract_form="services_food")

    items_list = docs._build_items_list_from_purchase_items(p)

    assert items_list[0]["menu_lines"] == [
        "День 1 — Завтрак (200,00 ₽): каша, чай; Обед (350,00 ₽): суп, второе; Ужин (300,00 ₽): рагу",
        "День 2 — Завтрак (200,00 ₽): каша, чай; Обед (350,00 ₽): суп, второе; Ужин (300,00 ₽): рагу",
    ]
    assert items_list[1]["menu_lines"] == []
