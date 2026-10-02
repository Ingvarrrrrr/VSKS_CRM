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


import re as _re

# Единственное место разбора ставки НДС строки в число (вида '22%', '20',
# '22/122' — легаси расчётное обозначение ФНС, см. ниже) — ПРАВИЛО №6.
# Раньше была продублирована в services/documents/stages_amounts.py
# (_parse_vat_rate_percent) — та функция теперь зовёт эту же.
def parse_vat_rate_percent(rate: Any) -> float:
    """Числовой процент из строки ставки НДС позиции ('5%', '20', '22/122',
    None/'Без НДС'/'ещё не знаю'). Нераспознанное или отсутствующее → 0.0."""
    if not rate:
        return 0.0
    s = str(rate).strip()
    m = _re.match(r'^(\d+(?:\.\d+)?)\s*%?$', s)
    if m:
        return float(m.group(1))
    m = _re.match(r'^(\d+(?:\.\d+)?)\s*/\s*\d+(?:\.\d+)?$', s)
    return float(m.group(1)) if m else 0.0


# ПРАВИЛО №6: единственное место формулы «НДС, выделенный ИЗ суммы, которая
# уже включает НДС» (total × p / (100 + p)). Раньше была продублирована в
# services/documents/stages_amounts.py (дважды), fabrikant_package.py,
# payment_vat.py — все четыре теперь зовут эту функцию.
def vat_included_amount(total: Any, rate: Any) -> Decimal:
    pct = parse_vat_rate_percent(rate)
    if pct <= 0:
        return Decimal("0")
    total_d = _dec(total)
    return _q2(total_d * Decimal(str(pct)) / (Decimal("100") + Decimal(str(pct))))


# ПРАВИЛО №6: единственное место, решающее «действует ли у ЭТОЙ строки флаг
# „НДС сверху"» — per_item берёт флаг строки, а null наследует флаг шапки;
# uniform всегда берёт флаг шапки. Второго места с этим if/else не заводить —
# и бэк (line_total ниже, документы), и перевод заявки в закупку обязаны
# звать эту функцию, а не читать item.vat_on_top напрямую.
def effective_vat_on_top(item_flag: Optional[bool], header_flag: Optional[bool], vat_mode: Optional[str]) -> bool:
    if (vat_mode or "uniform") == "per_item" and item_flag is not None:
        return bool(item_flag)
    return bool(header_flag)


# ПРАВИЛО №6: единственное место, решающее, КАКАЯ ставка НДС действует у
# строки — зеркало фронтового effectiveVatRateForItem (useVatCalc.ts:149-156).
# В режиме uniform у строки нет своего поля ввода ставки (vat_rate строки
# всегда None) — ставка берётся из шапки (purchase.vat_rate/wish.vat_rate),
# но только если шапка вообще применяет НДС (vat_applicable=True); иначе
# ставки нет вовсе (None), а не 0 — line_total/parse_vat_rate_percent сами
# трактуют пусто как «без НДС». В режиме per_item — всегда ставка строки,
# шапка не подмешивается. Второго парсера ставки не заводить — возврат идёт
# в том же виде (int/str/None), что понимает parse_vat_rate_percent.
def effective_vat_rate(
    item_rate: Any,
    vat_mode: Optional[str],
    header_applicable: Optional[bool],
    header_rate: Any,
) -> Any:
    if (vat_mode or "uniform") == "per_item":
        return item_rate
    if item_rate not in (None, ""):
        return item_rate
    return header_rate if header_applicable else None


# ПРАВИЛО №6: единственное место, считающее цену за единицу ДЛЯ ПЕЧАТИ В
# ДОКУМЕНТЕ (ТЗ/договор) — задача владельца (02.10.2026): при «НДС сверху»
# unit_price хранится БЕЗ налога, а в документе печатается цена ВКЛЮЧАЯ НДС
# (сумма/кол-во), сумма и «в т.ч. НДС» не меняются. Без надбавки — обычная
# unit_price как есть. Нулевое/пустое количество → unit_price как есть (без
# деления на ноль).
def document_unit_price(unit_price: Any, total: Any, quantity: Any, on_top: bool) -> Decimal:
    if on_top:
        qty = _dec(quantity)
        if qty != 0:
            return _q2(_dec(total) / qty)
    return _dec(unit_price)


def line_total(quantity: Any, unit_price: Any, rate: Any = None, on_top: bool = False) -> Decimal:
    """Обычная позиция (item_form=None): итог = количество × цена за единицу,
    округление до копеек. Единственное место с этим умножением — все места
    импорта/копирования, которые раньше писали `quantity * unit_price` инлайн,
    теперь вызывают эту функцию (см. докстринг модуля).

    on_top=True и ставка > 0 (см. parse_vat_rate_percent — «Без НДС»/«ещё не
    знаю»/пустая ставка дают 0.0, то есть БЕЗ надбавки) → НДС сверху: итог =
    количество × цена × (1 + p/100), округление до копеек в конце. Иначе —
    прежняя формула (цена уже включает НДС, если он есть)."""
    qty = _dec(quantity)
    price = _dec(unit_price)
    if on_top:
        pct = parse_vat_rate_percent(rate)
        if pct > 0:
            return _q2(qty * price * (Decimal("1") + Decimal(str(pct)) / Decimal("100")))
    return _q2(qty * price)


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


def _food_quantity(extra: dict) -> Decimal:
    """Питание: quantity = человек × приёмов пищи в день × дней (цена за приём —
    обычный unit_price позиции, здесь не участвует). Человек=0 → 0 (нет людей —
    нет расхода); приёмов пищи и дней — по аналогии с _accommodation_nights:
    пусто/не задано трактуем как 1, а не 0, иначе забытое поле молча обнуляет
    весь расчёт вместо явного «человек=0»."""
    persons = _dec(extra.get("persons"))
    meals_raw = extra.get("meals_per_day")
    meals = _dec(meals_raw) if meals_raw not in (None, "") else Decimal("1")
    days_raw = extra.get("days")
    days = _dec(days_raw) if days_raw not in (None, "") else Decimal("1")
    return persons * meals * days


def _food_menu_meals_total_price(menu: Any) -> tuple[Decimal, int]:
    """Питание, режим «меню по дням»: сумма цен ВСЕХ приёмов ВСЕХ дней (цена
    — за приём на человека) и общее число приёмов — единственное место,
    читающее структуру extra['menu'] (список дней [{day, meals: [{name,
    description, price}]}]); item_form_summary.py импортирует эту же функцию
    для текстового описания, второй копии обхода структуры не заводить
    (Правило №6). Мусор в структуре (не список/не dict) молча пропускается —
    не должен валить расчёт суммы."""
    total = Decimal("0")
    count = 0
    if isinstance(menu, list):
        for day in menu:
            if not isinstance(day, dict):
                continue
            meals = day.get("meals")
            if not isinstance(meals, list):
                continue
            for meal in meals:
                if not isinstance(meal, dict):
                    continue
                total += _dec(meal.get("price"))
                count += 1
    return total, count


def _food_menu_amounts(extra: dict) -> tuple[Decimal, Decimal, Decimal]:
    """Питание, режим «меню по дням»: итог = человек × Σ(price всех приёмов
    всех дней). Для совместимости с обычной позицией (quantity × unit_price)
    quantity = человек × (приёмов всего), unit_price = итог / quantity —
    ПРОИЗВОДНОЕ значение (тот же приём, что unit_price у transport в режиме
    «стоимость рейса вручную» — см. _transport_quantity_and_rate), с фронта
    не принимается. 0 человек или пустое меню → 0/0/0, без деления на ноль."""
    persons = _dec(extra.get("persons"))
    per_person_total, meals_count = _food_menu_meals_total_price(extra.get("menu"))
    quantity = persons * Decimal(meals_count)
    total = _q2(persons * per_person_total)
    unit_price = _q2(total / quantity) if quantity != 0 else Decimal("0")
    return quantity, unit_price, total


def _transport_quantity_and_rate(item: Any, extra: dict) -> tuple[Decimal, Decimal]:
    cost_mode = extra.get("cost_mode") or "hours"
    if cost_mode == "trip":
        return Decimal("1"), _dec(extra.get("trip_cost"))
    work_hours = _dec(extra.get("work_hours"))
    supply_hours_raw = extra.get("supply_hours")
    supply_hours = _dec(supply_hours_raw) if supply_hours_raw not in (None, "") else Decimal("2")
    return work_hours + supply_hours, _dec(extra.get("hourly_rate"))


def compute_item_total(
    item: Any, item_form: Optional[str], vat_on_top: bool = False, vat_rate: Any = "__unset__",
) -> Decimal:
    """Считает `total_price`, НЕ мутируя `item` — используй для превью/проверок
    (гейты «ТЗ не выше плана» и т.п.). Для реальной записи позиции — apply_item_amounts.

    vat_on_top (задача «НДС сверху», 02.10.2026) — только для обычной позиции
    (item_form=None, ветка line_total ниже); спец-формы (accommodation/
    transport/food) НДС-надбавку не считают (владелец не просил — у них
    unit_price вводится/выводится отдельными правилами формы).

    vat_rate (дефект «НДС сверху» в uniform, 02.10.2026) — ставка для ветки
    line_total; по умолчанию (сентинел "__unset__") читается item.vat_rate как
    раньше. Передавай сюда ТОЛЬКО результат effective_vat_rate() — при
    vat_mode='uniform' у строки нет своего поля ввода ставки, item.vat_rate
    всегда None, и без явного override формула резолвила ставку в 0% (см.
    effective_vat_rate в этом же модуле, зеркалит фронтовый
    effectiveVatRateForItem)."""
    extra = _extra(item)
    if item_form == "accommodation":
        qty = _accommodation_quantity(extra)
        nights = _accommodation_nights(extra)
        unit_price = _dec(getattr(item, "unit_price", None))
        return _q2(unit_price * qty * nights)
    if item_form == "transport":
        qty, unit_price = _transport_quantity_and_rate(item, extra)
        return _q2(qty * unit_price)
    if item_form == "food":
        mode = extra.get("mode") or "simple"
        if mode == "menu":
            _, _, total = _food_menu_amounts(extra)
            return total
        qty = _food_quantity(extra)
        unit_price = _dec(getattr(item, "unit_price", None))
        return _q2(unit_price * qty)
    _rate = getattr(item, "vat_rate", None) if vat_rate == "__unset__" else vat_rate
    return line_total(
        getattr(item, "quantity", None), getattr(item, "unit_price", None),
        rate=_rate, on_top=vat_on_top,
    )


def apply_item_amounts(
    item: Any, item_form: Optional[str], vat_on_top: bool = False, vat_rate: Any = "__unset__",
) -> Decimal:
    """Выставляет quantity/unit_price/total_price на `item` по правилам формы
    и возвращает итоговую сумму. Для accommodation/transport quantity (и для
    transport ещё и unit_price) — ПРОИЗВОДНЫЕ от extra_attrs, не принимаются
    напрямую с фронта (см. план, раздел «Модель»); то же для food в режиме
    «меню по дням» (quantity И unit_price — производные).

    Владелец (2026-09-15): у форм со спец-полями («Проживание»/«Перевозки»/
    «Питание») ТИП позиции — всегда «услуга» (это явно услуга, не товар/
    работа); единственное место, проставляющее item_type для этих форм — сам
    выбор типа позиции на фронте (PurchaseItemsEditor.vue) forced-дефолтом
    зеркалит эту же проверку `if item_form`, второго списка форм не заводить
    (Правило №6)."""
    if item_form:
        item.item_type = "услуга"
    extra = _extra(item)
    if item_form == "accommodation":
        item.quantity = _accommodation_quantity(extra)
        # unit_price — цена за номер/человека в сутки, вводится пользователем
        # напрямую, здесь не пересчитывается.
    elif item_form == "transport":
        qty, unit_price = _transport_quantity_and_rate(item, extra)
        item.quantity = qty
        item.unit_price = unit_price
    elif item_form == "food":
        mode = extra.get("mode") or "simple"
        if mode == "menu":
            qty, unit_price, _total = _food_menu_amounts(extra)
            item.quantity = qty
            item.unit_price = unit_price
        else:
            item.quantity = _food_quantity(extra)
            # unit_price — цена за приём пищи, вводится пользователем напрямую.
    total = compute_item_total(item, item_form, vat_on_top=vat_on_top, vat_rate=vat_rate)
    item.total_price = total
    return total
