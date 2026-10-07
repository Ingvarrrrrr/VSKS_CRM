"""Реестр «форм позиций» — единый источник состава спец-полей для позиций
закупки (Правило №6), отдаваемый и бэку (compute_item_total/apply_item_amounts
в item_amounts.py), и фронту (GET /api/dictionaries/item-forms →
frontend/src/data/item_forms.json, генерируется backend/scripts/export_dictionaries.py).

Файл — только литералы верхнего уровня (ITEM_FORMS, CONTRACT_FORM_TO_ITEM_FORM),
без импортов ORM/БД: export_dictionaries.py читает его статически через `ast`
(тот же приём, что services/dictionaries.py — см. докстринг там), поэтому не
добавляй сюда логику, требующую живого приложения.

Формы (владелец, «Корректировки GALA 7 сентября», строки 1–5):
  - accommodation («Проживание»): переключатель «за номер / за человека»,
    итог = цена × (номера|люди) × суток.
  - transport («Перевозки автобусом»): «часы в работе» + «часы подачи»
    (по умолчанию 2) × ставка/час, либо переключатель на ручную стоимость рейса.
  - food («Питание», добавлено 2026-09-15, режим «просто»): итог = цена за
    приём × человек × приёмов пищи в день × дней.
  - food, режим «меню по дням» (владелец не принял «просто», 2026-09-15:
    «должен быть переключатель, ... а должно быть и по дням и человекам»):
    поле `mode` переключает simple/menu; в menu — `menu`: список дней
    [{day, meals: [{name, description, price}]}], цена — за приём НА
    ЧЕЛОВЕКА. Итог = человек × Σ(price всех приёмов всех дней); для
    совместимости с обычной позицией quantity = человек × (приёмов всего),
    unit_price = итог / quantity — ПРОИЗВОДНОЕ (как unit_price у transport в
    режиме «стоимость рейса»), с фронта не принимается (см. item_amounts.py
    ::_food_menu_amounts). Вложенный редактор меню не ложится в generic
    рендер по списку fields — поле `menu` помечено `custom_editor:
    "food_menu"`, ItemFormFields.vue подключает по этому флагу
    components/items/FoodMenuEditor.vue.
"""
from __future__ import annotations

# code → {label, fields: [{key, label, type, options?, default?, hint?,
#         custom_editor?}], formula}
# type: text | number | select | date | datetime | switch | custom (custom —
# поле не рендерится generic-рендером ItemFormFields.vue, а подключает
# компонент по custom_editor, см. food.menu ниже; date — дата без времени,
# datetime — дата+время)
ITEM_FORMS = {
    "accommodation": {
        "label": "Проживание",
        "formula": "Итог = цена × (номера или люди, по переключателю) × суток",
        "fields": [
            {"key": "room_category", "label": "Категория номера", "type": "text"},
            {
                "key": "price_basis",
                "label": "Цена указана за",
                "type": "select",
                "options": [
                    {"value": "room", "label": "Номер"},
                    {"value": "person", "label": "Человека"},
                ],
                "default": "room",
                "hint": "Цена указана за номер в сутки / за человека в сутки",
            },
            {"key": "rooms", "label": "Номеров", "type": "number", "default": 0},
            {"key": "persons", "label": "Человек", "type": "number", "default": 0},
            {"key": "nights", "label": "Суток", "type": "number", "default": 1},
        ],
    },
    "transport": {
        "label": "Перевозки автобусом",
        "formula": (
            "Итог = ставка за час × (часы в работе + часы подачи) — режим «по часам»; "
            "либо введённая стоимость рейса — режим «стоимость рейса вручную»"
        ),
        "fields": [
            {"key": "place_from", "label": "Откуда", "type": "text"},
            {"key": "place_to", "label": "Куда", "type": "text"},
            {"key": "persons", "label": "Человек", "type": "number", "default": 0},
            {"key": "depart_at", "label": "Отправление", "type": "datetime"},
            {"key": "finish_at", "label": "Окончание", "type": "datetime"},
            {"key": "work_hours", "label": "Часы в работе", "type": "number", "default": 0},
            {
                "key": "supply_hours",
                "label": "Часы подачи",
                "type": "number",
                "default": 2,
                "hint": "часы подачи, обычно 2",
            },
            {"key": "hourly_rate", "label": "Ставка за час", "type": "number", "default": 0},
            {
                "key": "cost_mode",
                "label": "Расчёт стоимости",
                "type": "switch",
                "options": [
                    {"value": "hours", "label": "По часам"},
                    {"value": "trip", "label": "Стоимость рейса вручную"},
                ],
                "default": "hours",
                "hint": "«По часам» — ставка × (работа + подача); «Стоимость рейса вручную» — вводится готовая сумма",
            },
            {"key": "trip_cost", "label": "Стоимость рейса", "type": "number", "default": 0},
        ],
    },
    # flight/train (задача владельца 30.09, п. С4 — «вариант для перевозки
    # самолётом и поездом, приобретаются билеты соответственно»): поля
    # идентичны по смыслу (откуда/куда/даты/пассажиры/класс/цена билета),
    # различается только набор вариантов класса (fare_class) — два разных
    # ключа ITEM_FORMS, а не один с условной веткой, чтобы класс не путался
    # между видами транспорта в UI (экономический для самолёта ≠ плацкарт).
    # Формула — item_amounts.py::_flight_train_quantity: итог = пассажиров ×
    # цена билета × (2, если «цена за один конец» и указана дата обратно,
    # иначе 1). price_basis по умолчанию «туда-обратно» — цена уже введена
    # как полная (владелец: «по умолчанию туда-обратно = как введено»).
    "flight": {
        "label": "Авиабилеты",
        "formula": (
            "Итог = пассажиров × цена билета × 2 (если цена за один конец И указана "
            "дата обратно), иначе × 1"
        ),
        "fields": [
            {"key": "place_from", "label": "Откуда", "type": "text"},
            {"key": "place_to", "label": "Куда", "type": "text"},
            {"key": "date_to", "label": "Дата туда", "type": "date"},
            {
                "key": "date_back",
                "label": "Дата обратно",
                "type": "date",
                "hint": "необязательно; не раньше даты туда",
            },
            {"key": "passengers", "label": "Пассажиров", "type": "number", "default": 1},
            {
                "key": "fare_class",
                "label": "Класс",
                "type": "select",
                "options": [
                    {"value": "economy", "label": "Эконом"},
                    {"value": "business", "label": "Бизнес"},
                ],
                "default": "economy",
            },
            {"key": "ticket_price", "label": "Цена билета", "type": "number", "default": 0},
            {
                "key": "price_basis",
                "label": "Цена указана за",
                "type": "switch",
                "options": [
                    {"value": "round_trip", "label": "Туда-обратно"},
                    {"value": "one_way", "label": "Один конец"},
                ],
                "default": "round_trip",
                "hint": "«Один конец» и указана дата обратно — итог умножается на 2",
            },
        ],
    },
    "train": {
        "label": "Железнодорожные билеты",
        "formula": (
            "Итог = пассажиров × цена билета × 2 (если цена за один конец И указана "
            "дата обратно), иначе × 1"
        ),
        "fields": [
            {"key": "place_from", "label": "Откуда", "type": "text"},
            {"key": "place_to", "label": "Куда", "type": "text"},
            {"key": "date_to", "label": "Дата туда", "type": "date"},
            {
                "key": "date_back",
                "label": "Дата обратно",
                "type": "date",
                "hint": "необязательно; не раньше даты туда",
            },
            {"key": "passengers", "label": "Пассажиров", "type": "number", "default": 1},
            {
                "key": "fare_class",
                "label": "Класс",
                "type": "select",
                "options": [
                    {"value": "platskart", "label": "Плацкарт"},
                    {"value": "kupe", "label": "Купе"},
                    {"value": "sv", "label": "СВ"},
                    {"value": "seated", "label": "Сидячий"},
                ],
                "default": "kupe",
            },
            {"key": "ticket_price", "label": "Цена билета", "type": "number", "default": 0},
            {
                "key": "price_basis",
                "label": "Цена указана за",
                "type": "switch",
                "options": [
                    {"value": "round_trip", "label": "Туда-обратно"},
                    {"value": "one_way", "label": "Один конец"},
                ],
                "default": "round_trip",
                "hint": "«Один конец» и указана дата обратно — итог умножается на 2",
            },
        ],
    },
    "food": {
        "label": "Питание",
        "formula": (
            "Режим «просто»: итог = цена за приём × человек × приёмов пищи в "
            "день × дней. Режим «меню по дням»: итог = человек × сумма цен "
            "всех приёмов всех дней (цена — за приём на человека); quantity = "
            "человек × приёмов всего, unit_price = итог / quantity — "
            "производное значение"
        ),
        # Названия приёмов по умолчанию для нового дня в режиме «меню по
        # дням» — единственный источник (владелец: «по умолчанию завтрак/
        # обед/ужин, можно добавить/убрать/переименовать»), читает
        # components/items/FoodMenuEditor.vue через item_forms.json, второй
        # копии списка на фронте не заводить.
        "default_meal_names": ["Завтрак", "Обед", "Ужин"],
        "fields": [
            {
                "key": "mode",
                "label": "Режим ввода",
                "type": "switch",
                "options": [
                    {"value": "simple", "label": "Просто"},
                    {"value": "menu", "label": "Меню по дням"},
                ],
                "default": "simple",
                # Владелец (2026-09-15, оформление позиций закупки): длинная
                # подсказка-абзац под переключателем «даже мне не читаемо» —
                # подписи вариантов ("Просто"/"Меню по дням") самодостаточны,
                # короткая фраза вместо абзаца.
                "hint": "по дням — своя раскладка приёмов",
            },
            {"key": "persons", "label": "Человек", "type": "number", "default": 0},
            {
                "key": "meals_per_day",
                "label": "Приёмов пищи в день",
                "type": "number",
                "default": 3,
                "hint": "обычно 3: завтрак, обед, ужин",
            },
            {"key": "days", "label": "Дней", "type": "number", "default": 1},
            {
                "key": "menu",
                "label": "Меню по дням",
                "type": "custom",
                "custom_editor": "food_menu",
                "default": [],
                "hint": "цена — за приём на одного человека",
            },
        ],
    },
}


# Purchase.contract_form (см. app/models/purchase.py, app/services/documents/doc_types.py)
# → код формы позиций из ITEM_FORMS выше. Значения contract_form, отсутствующие
# здесь (обычные «Услуги», «Поставка» и т.д.) — обычная форма, item_form = None.
CONTRACT_FORM_TO_ITEM_FORM = {
    "services_food": "food",
    "services_accommodation": "accommodation",
    "services_transport": "transport",
    # Заявка/закупка на авиа- и ж/д билеты (владелец, п. С4) — те же правила
    # переноса, что у остальных CONTRACT_FORM_TO_ITEM_FORM (одна форма на весь
    # договор, см. item_form_for_row).
    "services_flight": "flight",
    "services_train": "train",
}


# «Проживание и питание» (владелец, решение по задаче): договор, где КАЖДАЯ
# строка — либо проживание, либо питание, выбор переключателем на строке, а
# не один item_form на всю закупку/заявку (как у остальных CONTRACT_FORM_TO_
# ITEM_FORM выше). Хранится PurchaseItem/WishItem/ContractItem.item_form
# (миграция w7x8y9z0a1b2) — «выбранное на предыдущем этапе не меняется само»
# (Lessons.md), поэтому колонка, а не эвристика по названию/содержимому.
# Значение — допустимые формы строки, первая — дефолт для новой строки.
CONTRACT_FORM_ROW_CHOICES = {
    "services_accommodation_food": ["accommodation", "food"],
}


def item_form_for_row(contract_form: str | None, row_item_form: str | None = None) -> str | None:
    """Эффективная форма ОДНОЙ строки позиции — ЕДИНСТВЕННЫЙ источник (Правило
    №6), которым обязаны пользоваться все расчёты/документы по строке.

    - contract_form без спец-формы (обычные «Услуги», «Поставка» и т.д.) —
      None, row_item_form не важен.
    - contract_form с ОДНОЙ формой на весь договор (CONTRACT_FORM_TO_ITEM_FORM:
      food/accommodation/transport) — эта форма, row_item_form не важен
      (строка своего item_form не хранит — как и раньше).
    - contract_form, допускающий ВЫБОР форм на строке (CONTRACT_FORM_ROW_CHOICES,
      сейчас только «Проживание и питание») — row_item_form, если он входит в
      допустимые для этого contract_form; иначе первая форма списка — дефолт
      для новой строки, ещё не выбравшей форму."""
    if not contract_form:
        return None
    choices = CONTRACT_FORM_ROW_CHOICES.get(contract_form)
    if choices:
        if row_item_form in choices:
            return row_item_form
        return choices[0]
    return CONTRACT_FORM_TO_ITEM_FORM.get(contract_form)


def item_form_for_purchase(purchase) -> str | None:
    """Форма позиций закупки — ЕДИНЫЙ источник на весь договор (contract_form
    самой закупки). Для contract_form из CONTRACT_FORM_ROW_CHOICES (несколько
    форм на строку) НЕ годится — здесь нет конкретной строки, чтобы разрешить
    выбор; такие вызовы должны использовать item_form_for_purchase_item
    (строка берётся по позиции) ниже."""
    if purchase is None:
        return None
    contract_form = getattr(purchase, "contract_form", None)
    if not contract_form:
        return None
    return CONTRACT_FORM_TO_ITEM_FORM.get(contract_form)


def item_form_for_wish(wish) -> str | None:
    """Форма позиций заявки — тот же CONTRACT_FORM_TO_ITEM_FORM, читающий
    wish.contract_form (владелец, 2026-09-15: «договора на перевозку и питание
    могут быть не только рамочные, но и разовые» — заявка обязана заводить
    спец-форму ДО конвертации в закупку, не только после). Логика намеренно
    зеркалит item_form_for_purchase выше — единственная разница источник
    (Wish вместо Purchase), формулы/реестр ITEM_FORMS общие и не дублируются.
    Как и item_form_for_purchase — не годится для CONTRACT_FORM_ROW_CHOICES,
    см. item_form_for_wish_item ниже."""
    if wish is None:
        return None
    contract_form = getattr(wish, "contract_form", None)
    if not contract_form:
        return None
    return CONTRACT_FORM_TO_ITEM_FORM.get(contract_form)


def item_form_for_purchase_item(purchase, item) -> str | None:
    """Эффективная форма ОДНОЙ позиции закупки — читает purchase.contract_form
    и item.item_form через item_form_for_row (см. выше). Единственное место,
    которое обязаны звать расчёты/документы ПО СТРОКЕ (apply_item_amounts/
    compute_item_total/item_form_summary) — замена «одна форма на всю закупку»
    там, где contract_form допускает выбор на строке."""
    contract_form = getattr(purchase, "contract_form", None) if purchase is not None else None
    row_item_form = getattr(item, "item_form", None) if item is not None else None
    return item_form_for_row(contract_form, row_item_form)


def item_form_for_wish_item(wish, item) -> str | None:
    """Зеркало item_form_for_purchase_item для заявки (см. его докстринг) —
    wish.contract_form + item.item_form строки."""
    contract_form = getattr(wish, "contract_form", None) if wish is not None else None
    row_item_form = getattr(item, "item_form", None) if item is not None else None
    return item_form_for_row(contract_form, row_item_form)
