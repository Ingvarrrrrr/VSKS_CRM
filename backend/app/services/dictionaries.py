"""Единый источник истины (Правило №6) для словарей статусов/подстатусов/
типов договора/способов и оснований закупки.

История: эти словари жили только в app/routers/purchase_export.py (комментарий
там же объяснял, что это «единый источник для purchases.py, wishes.py,
feo_planned_items.py и services/purchase_summary.py» — но по факту это была
попытка единого источника ВНУТРИ роутера, а не отдельный модуль, доступный без
импорта роутера). Перенесены сюда 1:1 (без изменения значений), в
purchase_export.py оставлены импорт-алиасы с теми же именами для обратной
совместимости существующих мест импорта (см. grep `_STATUS_LABELS` по
purchase_items_edit.py, services/purchase_summary.py, services/wish_distribution.py,
wishes.py, feo_planned_items.py — все продолжают импортировать из
app.routers.purchase_export, ничего в них менять не требуется).

Порядок статусов (STATUS_ORDER) НЕ дублируется — переиспользуется из
app.routers.purchases (там же, где он используется для канбана/фильтров),
см. backend/app/routers/dictionaries.py::get_purchase_dictionaries.
"""

PURCHASE_METHOD_LABELS = {
    "single":        "Единственный поставщик",
    "competitive":   "Конкурентная процедура",
    "quote_request": "Запрос котировок",
    "advance":       "Авансовый отчёт",
}

PURCHASE_BASIS_LABELS = {
    "plan_schedule": "план закупок",
    "service_note":  "служебная записка",
}

CONTRACT_TYPE_LABELS = {
    "single":                "Разовая поставка",
    "framework_cumulative":  "Рамочный (нарастающий итог)",
    "framework_with_amount": "Рамочный (с указанием суммы)",
}

STATUS_LABELS = {
    "wishes":           "Желания сотрудников",
    "plan_schedule":    "План закупок",
    "work_in_progress": "Ведётся работа",
    "contracted":       "Заключён договор",
    "ordered":          "Заказано",
    "delivered":        "Поставлено",
    "paid":             "Оплачено",
}

SUBSTATUS_LABELS = {
    "tz_forming":              "Формирование ТЗ",
    "kp_collecting":           "Сбор КП",
    "on_platform":             "Размещено на площадке",
    "contractor_negotiations": "Переговоры с поставщиком",
    "contract_signing":        "Подписание договора",
}

# Purchase.contract_form (см. app/models/purchase.py) — семь типовых форм
# договора (+ frontend CreateOrderView.vue::contractFormOptions, который
# сейчас держит собственную копию подписей; см. GET /api/dictionaries/item-forms
# и export_dictionaries.py → frontend/src/data/item_forms.json, Правило №6).
# 'services_accommodation'/'services_transport' — item-forms-accommodation-
# transport.md (владелец, «Корректировки GALA 7 сентября»): формы позиций
# «Проживание»/«Перевозки автобусом», см. app/services/item_forms.py.
CONTRACT_FORM_LABELS = {
    "services":               "Услуги",
    "services_food":          "Услуги — питание",
    "services_accommodation": "Проживание",
    "services_transport":     "Перевозки автобусом",
    "goods_single":           "Поставка — разовый договор",
    "gph_individual":         "ГПХ с физ.лицом",
    "gph_individual_rid":     "ГПХ с физ.лицом, передача прав на РИД",
    "repair_vehicle":         "Договор на ремонт ТС",
    "repair_framework":       "Рамочный договор на ремонт ТС",
}
