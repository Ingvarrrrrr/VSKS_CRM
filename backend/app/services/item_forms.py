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
"""
from __future__ import annotations

# code → {label, fields: [{key, label, type, options?, default?, hint?}], formula}
# type: text | number | select | datetime | switch
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
}


# Purchase.contract_form (см. app/models/purchase.py, app/services/documents/doc_types.py)
# → код формы позиций из ITEM_FORMS выше. Значения contract_form, отсутствующие
# здесь (обычные «Услуги», «Поставка» и т.д.) — обычная форма, item_form = None.
CONTRACT_FORM_TO_ITEM_FORM = {
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
