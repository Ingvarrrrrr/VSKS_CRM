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
  - food, режим «просто» (добавлено 2026-09-15): «10 чел. × 3 приёма/день ×
    5 дн. × 250,00 ₽» — пустые meals_per_day/days трактуются как 1, ровно как
    в _food_quantity (item_amounts.py), чтобы описание не расходилось с суммой.
  - food, режим «меню по дням» (владелец не принял «просто», тот же день):
    краткая сводка «10 чел. × 2 дн., 6 приёмов — 1 700,00 ₽ на человека,
    итого 17 000,00 ₽» в item.form_summary; ПОЛНАЯ раскладка по дням/приёмам/
    составу — отдельно в item.menu_lines (см. item_menu_lines ниже, печатает
    docx-шаблон, а не эта функция).
  - обычная позиция (item_form=None) — пустая строка.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from app.services.documents.formatting import _fmt_date, _fmt_money
from app.services.item_amounts import _dec, _food_menu_meals_total_price


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


def _plural_ru(n: Decimal, one: str, few: str, many: str) -> str:
    """Простой словарь форм для целого количества (без стороннего
    плюрализатора — в проекте такого для количественных слов нет, только
    падежные склонения ФИО/должностей в documents/morphology.py, они сюда не
    подходят). Дробное количество (не должно происходить для приёмов пищи,
    но на всякий случай) — форма «few», как для «3,5 дня» в русском."""
    if n != n.to_integral_value():
        return few
    i = abs(int(n)) % 100
    if 11 <= i <= 14:
        return many
    i = i % 10
    if i == 1:
        return one
    if 2 <= i <= 4:
        return few
    return many


def _food_summary(item: Any, extra: dict) -> str:
    """Питание: режим «просто» — как раньше (человек × приёмов/день × дней ×
    цена за приём); режим «меню по дням» — своя короткая сводка
    (_food_menu_summary), полная раскладка по дням идёт отдельно в
    item_menu_lines (docx-шаблон печатает её абзацами под этой строкой, а не
    внутри неё — см. contract_tz.docx/tech_spec_contract.docx)."""
    mode = extra.get("mode") or "simple"
    if mode == "menu":
        return _food_menu_summary(extra)
    persons = _dec(extra.get("persons"))
    meals_raw = extra.get("meals_per_day")
    meals = _dec(meals_raw) if meals_raw not in (None, "") else Decimal("1")
    days_raw = extra.get("days")
    days = _dec(days_raw) if days_raw not in (None, "") else Decimal("1")
    price_str = _fmt_money(getattr(item, "unit_price", None))
    meal_word = _plural_ru(meals, "приём", "приёма", "приёмов")
    return (
        f"{_fmt_count(persons)} чел. × {_fmt_count(meals)} {meal_word}/день × "
        f"{_fmt_count(days)} дн. × {price_str} ₽"
    )


def _food_menu_summary(extra: dict) -> str:
    """Питание, режим «меню по дням»: «10 чел. × 2 дн., 6 приёмов —
    1 700,00 ₽ на человека, итого 17 000,00 ₽». Суммы — через
    _food_menu_meals_total_price (item_amounts.py), та же функция, что
    считает total_price/quantity/unit_price (Правило №6 — обход структуры
    меню не дублируется)."""
    persons = _dec(extra.get("persons"))
    per_person_total, meals_count = _food_menu_meals_total_price(extra.get("menu"))
    days_raw = extra.get("days")
    if days_raw not in (None, ""):
        days = _dec(days_raw)
    else:
        days = Decimal(len(extra.get("menu") or []))
    total = persons * per_person_total
    meal_word = _plural_ru(Decimal(meals_count), "приём", "приёма", "приёмов")
    return (
        f"{_fmt_count(persons)} чел. × {_fmt_count(days)} дн., "
        f"{meals_count} {meal_word} — {_fmt_money(per_person_total)} ₽ на человека, "
        f"итого {_fmt_money(total)} ₽"
    )


def _food_menu_lines(extra: dict) -> list[str]:
    """Полная раскладка меню по дням для ТЗ («День 1 — Завтрак (200,00 ₽):
    каша, чай; Обед (350,00 ₽): ...; Ужин (300,00 ₽): ...») — item_menu_lines
    зовёт это ТОЛЬКО для food+mode=menu, для всех остальных случаев (обычная
    позиция, food/просто, accommodation/transport) — пустой список (см.
    item_menu_lines ниже)."""
    menu = extra.get("menu")
    if not isinstance(menu, list):
        return []
    lines: list[str] = []
    for idx, day in enumerate(menu, start=1):
        if not isinstance(day, dict):
            continue
        day_num = day.get("day")
        day_label = _fmt_count(day_num) if day_num not in (None, "") else str(idx)
        meals = day.get("meals")
        meal_parts: list[str] = []
        if isinstance(meals, list):
            for meal in meals:
                if not isinstance(meal, dict):
                    continue
                name = (meal.get("name") or "").strip() or "Приём"
                price_str = _fmt_money(meal.get("price"))
                description = (meal.get("description") or "").strip()
                if description:
                    meal_parts.append(f"{name} ({price_str} ₽): {description}")
                else:
                    meal_parts.append(f"{name} ({price_str} ₽)")
        lines.append(f"День {day_label} — " + "; ".join(meal_parts))
    return lines


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
    if item_form not in ("accommodation", "transport", "food"):
        return ""
    extra = _extra(item)
    if item_form == "accommodation":
        return _accommodation_summary(item, extra)
    if item_form == "food":
        return _food_summary(item, extra)
    return _transport_summary(item, extra)


def item_menu_lines(item: Any, item_form: Optional[str]) -> list[str]:
    """Полная раскладка меню питания по дням для ТЗ (contract_tz.docx,
    tech_spec_contract.docx: `{%p for l in item.menu_lines %}{{ l }}{%p
    endfor %}` в ячейке названия позиции, следом за item.form_summary) —
    ЕДИНСТВЕННЫЙ писатель этого текста (Правило №6). Пустой список для всех
    случаев, кроме food+mode=menu (обычная позиция, food/просто,
    accommodation, transport) — ключ item.menu_lines в контексте документа
    ВСЕГДА присутствует (contexts.py прокидывает его для каждой позиции), но
    для них он пуст и цикл в шаблоне не печатает ни одного абзаца."""
    if item_form != "food":
        return []
    extra = _extra(item)
    if (extra.get("mode") or "simple") != "menu":
        return []
    return _food_menu_lines(extra)
