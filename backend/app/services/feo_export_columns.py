"""feo_export_columns.py — каталог столбцов выгрузки «Выгрузить ФЭО»
(GET /api/feo-categories/export).

ПРАВИЛО №6: единый механизм выбора столбцов (export_columns_catalog.py) и
единые канонические подписи столбцов из app.services.excel_column_names.
Колонка `name` («Наименование позиции») стоит первой, чтобы при открытии
файла в Excel сразу читалась древовидная иерархия с отступами.
"""
from __future__ import annotations

from typing import Optional

from app.services.excel_column_names import (
    COL_ACTIVE,
    COL_APPENDIX,
    COL_CODE,
    COL_CONTRACTOR,
    COL_CONTRACTOR_INN,
    COL_CONTRACT_AMOUNT,
    COL_CONTRACT_NUMBER,
    COL_CONTRACT_RESIDUAL,
    COL_FACT_QTY,
    COL_FACT_TOTAL,
    COL_FACT_UNIT_PRICE,
    COL_FEO_DIRECTION,
    COL_FEO_QTY,
    COL_FEO_SUBDIRECTION,
    COL_FEO_TOTAL,
    COL_FEO_TYPE,
    COL_FEO_UNIT_PRICE,
    COL_ITEM_NAME,
    COL_ITEM_TYPE,
    COL_NOTES,
    COL_ORDER_AMOUNT,
    COL_ORDER_NUMBER,
    COL_ORDERED,
    COL_PAID_AMOUNT_MONEY,
    COL_PAYMENT_AMOUNT,
    COL_PAYMENT_DATE,
    COL_PAYMENT_DOC_NUMBER,
    COL_PAYMENT_PURPOSE,
    COL_PLANNED_QTY,
    COL_PLANNED_TOTAL,
    COL_PLANNED_UNIT_PRICE,
    COL_PURCHASE_AMOUNT,
    COL_PURCHASE_NUMBER,
    COL_RESIDUAL,
    COL_ROW_ID,
    COL_ROW_TYPE,
    COL_TO_ORDER,
    COL_UNIT,
)
from app.services.export_columns_catalog import (
    column_index as _column_index,
    columns_catalog as _columns_catalog,
    headers_and_widths as _headers_and_widths,
    resolve_selected_keys as _resolve_selected_keys,
)

# Стадии шкалы выполнения
STAGE_DEFS: list[tuple] = [
    ("in_work", "Ведётся работа"),
    ("purchase_done", "Закупка проведена"),
    ("contracted", "Договор заключен (устно или письменно)"),
    ("ordered_flag", "Товар заказан"),
    ("delivered", "Товар поставлен"),
    ("paid_marked", "Оплачено"),
    ("paid_confirmed", "Подтверждено выпиской"),
]

# (key, label, group, ширина, default)
# Колонка `name` стоит первой (столбец A), чтобы дерево категорий и товаров
# сразу открывалось с визуальными отступами по уровням вложенности.
FEO_EXPORT_COLUMNS: list[tuple] = [
    # 1. Иерархия дерева (наименование с отступами)
    ("name", COL_ITEM_NAME, "План", 48, True),

    # 2–4. Плоские колонки уровней ФЭО (для фильтрации и сводных)
    ("feo_direction", COL_FEO_DIRECTION, "Категории ФЭО", 30, True),
    ("feo_type", COL_FEO_TYPE, "Категории ФЭО", 30, True),
    ("feo_subdirection", COL_FEO_SUBDIRECTION, "Категории ФЭО", 30, True),

    # 5–9. План позиции
    ("feo_unit", COL_UNIT, "План", 16, True),
    ("plan_qty", COL_PLANNED_QTY, "План", 20, True),
    ("plan_unit_price", COL_PLANNED_UNIT_PRICE, "План", 22, True),
    ("plan", COL_PLANNED_TOTAL, "План", 22, True),
    ("notes", COL_NOTES, "План", 25, True),

    # 10–12. Статусы и тип
    ("stage_status", "Правильный статус", "Статусы", 20, True),
    ("item_type", COL_ITEM_TYPE, "Статусы", 18, True),
    ("is_in_plan", "План закупок", "Стадии", 16, True),

    # 13–19. Стадии выполнения
    ("in_work", "Ведётся работа", "Стадии", 18, True),
    ("purchase_done", "Закупка проведена", "Стадии", 18, True),
    ("protocol_signed", "Подписание протокола", "Стадии", 20, True),
    ("contracted", "Договор заключен (устно или письменно)", "Стадии", 24, True),
    ("ordered_flag", "Товар заказан", "Стадии", 18, True),
    ("delivered", "Товар поставлен", "Стадии", 18, True),
    ("paid_marked", "Оплачено", "Стадии", 16, True),

    # 20–23. Факт и оплата
    ("fact_qty", COL_FACT_QTY, "Факт", 20, True),
    ("fact_unit_price", COL_FACT_UNIT_PRICE, "Факт", 22, True),
    ("fact_amount", COL_FACT_TOTAL, "Факт", 22, True),
    ("paid_amount_money", COL_PAID_AMOUNT_MONEY, "Факт", 20, True),

    # 24–27. Закупка и контрагент
    ("purchase_number", COL_PURCHASE_NUMBER, "Договор и закупки", 18, True),
    ("order_number", COL_ORDER_NUMBER, "Договор и закупки", 18, True),
    ("contractor_name", COL_CONTRACTOR, "Договор и закупки", 32, True),
    ("contractor_inn", COL_CONTRACTOR_INN, "Договор и закупки", 18, True),

    # Колонки заказа, договора и платежа
    ("purchase_amount", COL_PURCHASE_AMOUNT, "Договор и закупки", 24, True),
    ("payment_purpose", COL_PAYMENT_PURPOSE, "Закупки и платежи", 42, True),
    ("order_amount", COL_ORDER_AMOUNT, "Договор и закупки", 22, True),
    ("contract_number", COL_CONTRACT_NUMBER, "Договор и закупки", 22, True),
    ("contract_amount", COL_CONTRACT_AMOUNT, "Договор и закупки", 24, True),
    ("contract_residual", COL_CONTRACT_RESIDUAL, "Договор и закупки", 22, True),

    # Платежи и реквизиты
    ("payment_doc_number", COL_PAYMENT_DOC_NUMBER, "Закупки и платежи", 26, True),
    ("payment_date", COL_PAYMENT_DATE, "Закупки и платежи", 18, True),
    ("payment_amount", COL_PAYMENT_AMOUNT, "Закупки и платежи", 24, True),
    ("expense_group_code", "Код расходов", "Закупки и платежи", 18, True),
    ("payment_kbk", "Детализированный код / КБК", "Закупки и платежи", 24, True),
    ("payment_status", "Статус платежа", "Закупки и платежи", 18, True),
    ("paid_confirmed", "Подтверждено выпиской", "Стадии", 22, True),

    # Показатели ФЭО и остатки
    ("feo_qty", COL_FEO_QTY, "ФЭО", 18, True),
    ("feo_unit_price", COL_FEO_UNIT_PRICE, "ФЭО", 22, True),
    ("feo", COL_FEO_TOTAL, "ФЭО", 22, True),
    ("ordered", COL_ORDERED, "ФЭО", 20, True),
    ("to_order", COL_TO_ORDER, "ФЭО", 20, True),
    ("residual", COL_RESIDUAL, "ФЭО", 20, True),
    ("active", COL_ACTIVE, "ФЭО", 16, True),
    ("code", COL_CODE, "ФЭО", 16, False),
    ("app", COL_APPENDIX, "ФЭО", 14, False),
] + [
    (f"{key}_amt", f"{label}, ₽", "Суммы по стадиям", 22, True)
    for key, label in STAGE_DEFS
] + [
    ("row_type", COL_ROW_TYPE, "Служебное", 22, True),
    ("row_id", COL_ROW_ID, "Служебное", 20, True),
]

_BY_KEY = {k: (label, group, width) for k, label, group, width, _d in FEO_EXPORT_COLUMNS}
ALL_KEYS: list = [k for k, *_ in FEO_EXPORT_COLUMNS]
DEFAULT_KEYS: list = [k for k, _l, _g, _w, is_default in FEO_EXPORT_COLUMNS if is_default]
MONEY_KEYS: set = {
    "plan_unit_price", "plan",
    "fact_unit_price", "fact_amount", "paid_amount_money",
    "contract_amount", "purchase_amount", "order_amount",
    "payment_amount",
    "feo_unit_price", "feo", "ordered", "to_order", "residual",
} | {f"{k}_amt" for k, _ in STAGE_DEFS}

STAGE_TEXT_KEYS: tuple = (
    "is_in_plan", "in_work", "purchase_done", "protocol_signed",
    "contracted", "ordered_flag", "delivered", "paid_marked", "paid_confirmed",
    "active",
)
STAGE_AMOUNT_KEYS: tuple = tuple(f"{k}_amt" for k, _ in STAGE_DEFS)
HIDDEN_CATALOG_KEYS: set = {"row_id"}


def columns_catalog() -> list[dict]:
    return [c for c in _columns_catalog(FEO_EXPORT_COLUMNS) if c["key"] not in HIDDEN_CATALOG_KEYS]


def resolve_selected_keys(columns: Optional[str]) -> list:
    return _resolve_selected_keys(FEO_EXPORT_COLUMNS, columns, always=("name", "row_type", "row_id"))


def headers_and_widths(selected_keys: list) -> tuple:
    return _headers_and_widths(_BY_KEY, selected_keys)


def column_index(selected_keys: list, key: str) -> Optional[int]:
    return _column_index(selected_keys, key)
