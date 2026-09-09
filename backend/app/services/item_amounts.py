"""Единственный писатель `total_price`/`total`/`total` позиций закупки на бэке
(Правило №6). Раньше формула `quantity × unit_price` (и её частные случаи —
условный фоллбэк «если total_price не пришёл — посчитать») была продублирована
по ~15 местам (purchase_items_edit, purchases.py create/update, wishes.py,
wish_convert.py, wish_distribution.py, purchase_items_import*.py,
purchase_import_parser_group.py, receipts_creation.py/receipts_recompute.py,
purchase_ops.py) — см. grep `total_price\\s*=` backend/app в отчёте сессии
item-forms-accommodation-transport.md. Теперь везде вызывается либо
`line_total()` (голое умножение — обычная позиция, item_form=None), либо
`compute_item_total`/`apply_item_amounts` (позиция со спец-формой — «Проживание»/
«Перевозки», см. services/item_forms.py).

extra_attrs (JSONB на purchase_items/wish_items/contract_items) хранит поля
спец-формы (ITEM_FORMS[item_form]['fields']) — единственное хранилище, второго
не заводить (см. план, раздел «Принципы»).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

_CENTS = Decimal("0.01")


def _dec(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _q2(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def line_total(quantity: Any, unit_price: Any) -> Decimal:
    """Обычная позиция (item_form=None): итог = количество × цена за единицу,
    округление до копеек. Единственное место с этим умножением — все места
    импорта/копирования, которые раньше писали `quantity * unit_price` инлайн,
    теперь вызывают эту функцию (см. докстринг модуля)."""
    return _q2(_dec(quantity) * _dec(unit_price))


def _extra(item: Any) -> dict:
    extra = getattr(item, "extra_attrs", None)
    return extra if isinstance(extra, dict) else {}


def _accommodation_quantity(extra: dict) -> Decimal:
    price_basis = extra.get("price_basis") or "room"
    if price_basis == "person":
        return _dec(extra.get("persons"))
    return _dec(extra.get("rooms"))


def _accommodation_nights(extra: dict) -> Decimal:
    nights = extra.get("nights")
    nights_dec = _dec(nights) if nights not in (None, "") else Decimal("1")
    return nights_dec if nights_dec != 0 else Decimal("1")


def _transport_quantity_and_rate(item: Any, extra: dict) -> tuple[Decimal, Decimal]:
    cost_mode = extra.get("cost_mode") or "hours"
    if cost_mode == "trip":
        return Decimal("1"), _dec(extra.get("trip_cost"))
    work_hours = _dec(extra.get("work_hours"))
    supply_hours_raw = extra.get("supply_hours")
    supply_hours = _dec(supply_hours_raw) if supply_hours_raw not in (None, "") else Decimal("2")
    return work_hours + supply_hours, _dec(extra.get("hourly_rate"))


def compute_item_total(item: Any, item_form: Optional[str]) -> Decimal:
    """Считает `total_price`, НЕ мутируя `item` — используй для превью/проверок
    (гейты «ТЗ не выше плана» и т.п.). Для реальной записи позиции — apply_item_amounts."""
    extra = _extra(item)
    if item_form == "accommodation":
        qty = _accommodation_quantity(extra)
        nights = _accommodation_nights(extra)
        unit_price = _dec(getattr(item, "unit_price", None))
        return _q2(unit_price * qty * nights)
    if item_form == "transport":
        qty, unit_price = _transport_quantity_and_rate(item, extra)
        return _q2(qty * unit_price)
    return line_total(getattr(item, "quantity", None), getattr(item, "unit_price", None))


def apply_item_amounts(item: Any, item_form: Optional[str]) -> Decimal:
    """Выставляет quantity/unit_price/total_price на `item` по правилам формы
    и возвращает итоговую сумму. Для accommodation/transport quantity (и для
    transport ещё и unit_price) — ПРОИЗВОДНЫЕ от extra_attrs, не принимаются
    напрямую с фронта (см. план, раздел «Модель»)."""
    extra = _extra(item)
    if item_form == "accommodation":
        item.quantity = _accommodation_quantity(extra)
        # unit_price — цена за номер/человека в сутки, вводится пользователем
        # напрямую, здесь не пересчитывается.
    elif item_form == "transport":
        qty, unit_price = _transport_quantity_and_rate(item, extra)
        item.quantity = qty
        item.unit_price = unit_price
    total = compute_item_total(item, item_form)
    item.total_price = total
    return total
