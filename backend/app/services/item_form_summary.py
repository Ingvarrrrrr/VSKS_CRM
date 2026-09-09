"""Человекочитаемое описание позиции со спец-формой (Правило №6 — ЕДИНСТВЕННАЯ
функция, формирующая этот текст: документы (services/documents/contexts.py),
экспорт (routers/purchase_export.py) и позже фронт через API зовут ЕЁ, вторая
копия текста не заводится).

Источник состава полей — services/item_forms.py::ITEM_FORMS (не трогается
здесь, только читается). Денежные суммы форматируются существующим
services/documents/formatting.py::_fmt_money (без нового форматтера); дата в
depart_at — тем же _fmt_date плюс время (в проекте нет отдельного
datetime-форматтера для шаблонов, только средство даты).

item-forms-accommodation-transport.md, шаг 4:
  - accommodation: «Стандартный четырёхместный, 8 номеров × 6 600,00 ₽ × 3 сут.»
    либо «... за человека: 32 чел. × 6 600,00 ₽ × 3 сут.» (переключатель
    price_basis).
  - transport: «Москва → Курск, 32 чел., подача 07.05.2026 08:00, 5 ч работы +
    2 ч подачи × 1 500,00 ₽/ч» либо «... стоимость рейса 12 000,00 ₽»
    (переключатель cost_mode).
  - обычная позиция (item_form=None) — пустая строка.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.services.documents.formatting import _fmt_date, _fmt_money
from app.services.item_amounts import _dec


def _extra(item: Any) -> dict:
    extra = getattr(item, "extra_attrs", None)
    return extra if isinstance(extra, dict) else {}


def _fmt_count(value: Any) -> str:
    """Целое без «.0» (8, не 8.0); дробное — с запятой, как в остальных
    документах. Не денежный и не датовый формат — отдельный money/date
    хелпер сюда заводить незачем, это просто печать количества."""
    d = _dec(value)
    if d == d.to_integral_value():
        return str(int(d))
    return str(d).replace(".", ",")


def _fmt_datetime(value: Any) -> str:
    """Дата+время для «подача {depart_at}» — дата тем же _fmt_date, что и
    везде в документах, время добавляется отдельно (в проекте нет готового
    datetime-форматтера для шаблонов)."""
    if not value:
        return ""
    dt = value
    if isinstance(value, str):
        raw = value.strip()
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return raw
    date_part = _fmt_date(dt.date() if hasattr(dt, "date") else dt)
    if not hasattr(dt, "hour"):
        return date_part
    return f"{date_part} {dt.hour:02d}:{dt.minute:02d}"


def _accommodation_summary(item: Any, extra: dict) -> str:
    room_category = (extra.get("room_category") or "").strip()
    price_basis = extra.get("price_basis") or "room"
    nights = extra.get("nights")
    nights_str = _fmt_count(nights if nights not in (None, "") else 1)
    price_str = _fmt_money(getattr(item, "unit_price", None))

    parts = []
    if room_category:
        parts.append(room_category)
    if price_basis == "person":
        persons_str = _fmt_count(extra.get("persons"))
        parts.append(f"за человека: {persons_str} чел. × {price_str} ₽ × {nights_str} сут.")
    else:
        rooms_str = _fmt_count(extra.get("rooms"))
        parts.append(f"{rooms_str} номеров × {price_str} ₽ × {nights_str} сут.")
    return ", ".join(p for p in parts if p)


def _transport_summary(item: Any, extra: dict) -> str:
    place_from = (extra.get("place_from") or "").strip()
    place_to = (extra.get("place_to") or "").strip()
    persons = extra.get("persons")
    depart_at = extra.get("depart_at")
    cost_mode = extra.get("cost_mode") or "hours"

    parts = []
    if place_from or place_to:
        parts.append(f"{place_from} → {place_to}".strip(" →"))
    if persons not in (None, ""):
        parts.append(f"{_fmt_count(persons)} чел.")
    depart_str = _fmt_datetime(depart_at)
    if depart_str:
        parts.append(f"подача {depart_str}")

    if cost_mode == "trip":
        trip_cost_str = _fmt_money(extra.get("trip_cost"))
        parts.append(f"стоимость рейса {trip_cost_str} ₽")
    else:
        work_hours_raw = extra.get("work_hours")
        supply_hours_raw = extra.get("supply_hours")
        supply_hours = supply_hours_raw if supply_hours_raw not in (None, "") else 2
        rate_str = _fmt_money(extra.get("hourly_rate"))
        parts.append(
            f"{_fmt_count(work_hours_raw)} ч работы + {_fmt_count(supply_hours)} ч подачи × {rate_str} ₽/ч"
        )
    return ", ".join(p for p in parts if p)


def item_form_summary(item: Any, item_form: Optional[str]) -> str:
    """Человекочитаемая строка описания позиции по её спец-форме. Работает
    через getattr/extra_attrs — годится и для PurchaseItem/WishItem/
    ContractItem (ORM), и для SimpleNamespace в тестах. item_form=None
    (обычная позиция) — пустая строка."""
    if item_form not in ("accommodation", "transport"):
        return ""
    extra = _extra(item)
    if item_form == "accommodation":
        return _accommodation_summary(item, extra)
    return _transport_summary(item, extra)
