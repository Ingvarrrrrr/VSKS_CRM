"""Dropdown value sets for the purchase import-template (Excel DataValidation
+ «Справочники» sheet).

Each list holds tuples: (display_label, internal_key_or_None).
For fields where the display label is stored as-is (free text): only label, key=None.

Split out of purchase_import_template.py / purchase_export.py (refactor, 2026-09).

ПРАВИЛО №6 (один показатель — один источник истины): status/substatus/
contract_type/basis/method уже есть в app.services.dictionaries — читаем
оттуда, а не храним копию, ГДЕ наборы совпадают 1:1.
Наборы _DD_STATUS и _DD_METHOD НЕ совпадают с dictionaries.py построчно
(см. комментарии на местах) — поэтому остаются собственными литералами,
а не собираются из dictionaries.py.
"""
from app.services.dictionaries import (
    CONTRACT_TYPE_LABELS,
    SUBSTATUS_LABELS,
    PURCHASE_BASIS_LABELS,
)
from app.services.ru_regions import RU_REGIONS

# ---------------------------------------------------------------------------
# Наборы, идентичные dictionaries.py — переиспользуются (ПРАВИЛО №6),
# только меняем направление dict{key: label} → list[(label, key)] для DV.
# ---------------------------------------------------------------------------
_DD_CONTRACT_TYPE = [(label, key) for key, label in CONTRACT_TYPE_LABELS.items()]
_DD_SUBSTATUS = [(label, key) for key, label in SUBSTATUS_LABELS.items()]
_DD_BASIS = [(label, key) for key, label in PURCHASE_BASIS_LABELS.items()]

# ---------------------------------------------------------------------------
# _DD_STATUS — ОТЛИЧАЕТСЯ от dictionaries.py::STATUS_LABELS: здесь есть
# дополнительный alias-пункт «Поставлено, но не оплачено» → "delivered"
# (тот же ключ, что и «Поставлено» — это подсказка для импортёра, а не
# отдельный статус), которого в STATUS_LABELS нет. НЕ сливать: смысл разный
# (dictionaries.py — канонический display-label по ключу; здесь — все
# формулировки, которые пользователь может вписать при импорте).
# ---------------------------------------------------------------------------
_DD_STATUS = [           # label → key stored in status
    ("Желания сотрудников",        "wishes"),
    ("План закупок",                "plan_schedule"),
    ("Ведётся работа",             "work_in_progress"),
    ("Заключён договор",           "contracted"),
    ("Заказано",                   "ordered"),
    ("Поставлено",                 "delivered"),
    ("Поставлено, но не оплачено", "delivered"),
    ("Оплачено",                   "paid"),
]

# ---------------------------------------------------------------------------
# _DD_METHOD — ОТЛИЧАЕТСЯ от dictionaries.py::PURCHASE_METHOD_LABELS: там
# есть дополнительный ключ "advance" ("Авансовый отчёт"), которого здесь
# намеренно нет — авансовый отчёт не выбирается через импорт-шаблон способом
# закупки. НЕ сливать.
# ---------------------------------------------------------------------------
_DD_METHOD = [           # label → key stored in purchase_method
    ("Единственный поставщик",  "single"),
    ("Конкурентная процедура",  "competitive"),
    ("Запрос котировок",        "quote_request"),
]

_DD_VAT_APPLICABLE = [   # just display values, stored as bool
    ("Да",   None),
    ("Нет",  None),
]
_DD_VAT_RATE = [         # stored as integer
    ("0",   None),
    ("10",  None),
    ("20",  None),
    ("22",  None),
]
_DD_PREPAYMENT = [
    ("Да",  None),
    ("Нет", None),
]
_DD_MONTHLY = [
    ("Да",  None),
    ("Нет", None),
]
_DD_ITEM_TYPE = [        # label → stored directly in item_type
    ("Товар",  "товар"),
    ("Услуга", "услуга"),
    ("Работа", "работа"),
]
_DD_PAYMENT_BASIS = [    # label → key stored in payment_basis_type
    ("Договор",      "contract"),
    ("Счёт",         "invoice"),
    ("Счёт-договор", "invoice_contract"),
]
_DD_UNIT = [             # free-text suggestions only
    ("шт",    None), ("пар",  None), ("комп.", None), ("кг",   None),
    ("л",     None), ("м",    None), ("м²",   None),  ("м³",   None),
    ("уп.",   None), ("набор",None), ("усл.", None),
]
_DD_QUARTER = [          # квартал принятия обязательств (1-4)
    ("1", None),
    ("2", None),
    ("3", None),
    ("4", None),
]
_DD_VAT_MODE = [         # режим НДС
    ("Одинаковый",          "uniform"),
    ("Для каждого товара",  "per_item"),
]

# 89 субъектов РФ — для поля delivery_region (регион поставки, без спец-значений)
_DD_DELIVERY_REGION: list[tuple[str, str]] = [
    (name, name) for name in sorted(RU_REGIONS.keys())
]

# 89 субъектов + спец-значения — для поля region (регион проведения мероприятия)
_DD_EVENT_REGION: list[tuple[str, str]] = [
    ("Не определён",         "Не определён"),
    ("Несколько регионов",   "Несколько регионов"),
    ("Федеральное мероприятие", "Федеральное мероприятие"),
] + _DD_DELIVERY_REGION
