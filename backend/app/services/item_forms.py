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
# type: text | number | select | datetime | switch | custom (custom — поле не
# рендерится generic-рендером ItemFormFields.vue, а подключает компонент по
# custom_editor, см. food.menu ниже)
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
}


def item_form_for_purchase(purchase) -> str | None:
    """Форма позиций закупки — ЕДИНСТВЕННЫЙ источник (contract_form самой
    закупки), позиция/заявка своего item_form не хранит (см. докстринг модуля
    и план item-forms-accommodation-transport.md, раздел «Модель»)."""
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
    (Wish вместо Purchase), формулы/реестр ITEM_FORMS общие и не дублируются."""
    if wish is None:
        return None
    contract_form = getattr(wish, "contract_form", None)
    if not contract_form:
        return None
    return CONTRACT_FORM_TO_ITEM_FORM.get(contract_form)
