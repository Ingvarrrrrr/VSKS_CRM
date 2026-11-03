"""feo_export_columns.py — каталог столбцов выгрузки «Выгрузить ФЭО»
(GET /api/feo-categories/export, задача владельца 20.10.2026).

ПРАВИЛО №6: тот же приём выбора столбцов, что уже есть у плана-графика
(app.services.plan_graph_export_columns.PLAN_GRAPH_COLUMNS/columns_catalog/
resolve_selected_keys) — форма [{key,label,group,width,default}], тот же
смысл query-параметра `columns` (через запятую, неизвестные ключи
игнорируются, пусто/нет → ТОЛЬКО default=True). Общий хелпер вынесен в
app.services.export_columns_catalog (columns_catalog/resolve_selected_keys/
headers_and_widths/column_index, параметризованы списком колонок) и
переиспользован ОБОИМИ модулями — второй алгоритм парсинга `columns` не
заводим.
"""
from __future__ import annotations

from typing import Optional

from app.services.export_columns_catalog import (
    column_index as _column_index,
    columns_catalog as _columns_catalog,
    headers_and_widths as _headers_and_widths,
    resolve_selected_keys as _resolve_selected_keys,
)

# Стадии шкалы выполнения (подписи согласованы со структурой GoodsService владельца)
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
# Задача владельца 03.11.2026: первые 27 колонок идут строго в порядке структуры GoodsService:
# «Направление расходов по категориям в соответствии с ФЭО», «Тип расходов в соответствии с ФЭО Конкретизированный»,
# «Направление расходов из приложений к ФЭО», «Наименование товара», «Ед. изм. (ОКЕИ)», «Плановое количество»,
# «Плановая цена», «Плановая стоимость за объём», «Комментарий», «Правильный статус», «Товары или Услуги»,
# «План закупок», «Ведётся работа», «Закупка проведена», «Подписание протокола», «Договор заключен (устно или письменно)»,
# «Товар заказан», «Товар поставлен», «Оплачено», «Факт: Количество», «Итоговая цена за единицу товара»,
# «Итоговая цена за объём», «Оплачено в деньгах», «№ Закупки», «№ Заявки», «Контрагент», «ИНН Контрагента».
# Остальные используемые колонки (договоры, платежи, КБК, остатки, суммы) следуют за ними.
FEO_EXPORT_COLUMNS: list[tuple] = [
    # 1–3. Категории и направления ФЭО
    ("feo_direction", "Направление расходов по категориям в соответствии с ФЭО", "Категории ФЭО", 35, True),
    ("feo_type", "Тип расходов в соответствии с ФЭО Конкретизированный", "Категории ФЭО", 35, True),
    ("feo_subdirection", "Направление расходов из приложений к ФЭО", "Категории ФЭО", 35, True),

    # 4–9. План позиции
    ("name", "Наименование товара", "План", 45, True),
    ("feo_unit", "Ед. изм. (ОКЕИ)", "План", 16, True),
    ("plan_qty", "Плановое количество", "План", 18, True),
    ("plan_unit_price", "Плановая цена", "План", 18, True),
    ("plan", "Плановая стоимость за объём", "План", 22, True),
    ("notes", "Комментарий", "План", 25, True),

    # 10–12. Статусы и тип
    ("stage_status", "Правильный статус", "Статусы", 20, True),
    ("item_type", "Товары или Услуги", "Статусы", 18, True),
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
    ("fact_qty", "Факт: Количество", "Факт", 18, True),
    ("fact_unit_price", "Итоговая цена за единицу товара", "Факт", 22, True),
    ("fact_amount", "Итоговая цена за объём", "Факт", 22, True),
    ("paid_amount_money", "Оплачено в деньгах", "Факт", 20, True),

    # 24–27. Закупка и контрагент
    ("purchase_number", "№ Закупки", "Договор и закупки", 16, True),
    ("order_number", "№ Заявки", "Договор и закупки", 16, True),
    # 26–27. Контрагент
    ("contractor_name", "Контрагент", "Договор и закупки", 32, True),
    ("contractor_inn", "ИНН Контрагента", "Договор и закупки", 18, True),

    # --- Колонки заказа, договора и платежа (задача владельца 03.11.2026) ---
    ("purchase_amount", "Сумма закупки / заказа (₽)", "Договор и закупки", 24, True),
    ("payment_purpose", "Назначение платежа", "Закупки и платежи", 42, True),
    ("order_amount", "Сумма заявки (₽)", "Договор и закупки", 22, True),
    ("contract_number", "Номер договора", "Договор и закупки", 22, True),
    ("contract_amount", "Сумма по договору (₽)", "Договор и закупки", 24, True),
    ("contract_residual", "Остаток по договору (₽)", "Договор и закупки", 22, True),

    # Платежи и реквизиты
    ("payment_doc_number", "Номер платёжного документа", "Закупки и платежи", 26, True),
    ("payment_date", "Дата платежа", "Закупки и платежи", 16, True),
    ("payment_amount", "Сумма платёжного документа (₽)", "Закупки и платежи", 24, True),
    ("expense_group_code", "Код расходов", "Закупки и платежи", 18, True),
    ("payment_kbk", "Детализированный код / КБК", "Закупки и платежи", 24, True),
    ("payment_status", "Статус платежа", "Закупки и платежи", 18, True),
    ("paid_confirmed", "Подтверждено выпиской", "Стадии", 22, True),

    # Показатели ФЭО и остатки
    ("feo_qty", "Кол-во по ФЭО", "ФЭО", 16, True),
    ("feo_unit_price", "Цена за ед. по ФЭО (₽)", "ФЭО", 20, True),
    ("feo", "Финансирование по ФЭО (₽)", "ФЭО", 22, True),
    ("ordered", "Заказано (₽)", "ФЭО", 20, True),
    ("to_order", "Надо заказать (₽)", "ФЭО", 20, True),
    ("residual", "Остаток (₽)", "ФЭО", 20, True),
    ("active", "Активна", "ФЭО", 16, True),
    ("code", "Код", "ФЭО", 16, False),
    ("app", "Прил.", "ФЭО", 14, False),
] + [
    # Суммы по стадиям (в деньгах, сдвинуты в конец для сводных отчётов)
    (f"{key}_amt", f"{label}, ₽", "Суммы по стадиям", 22, True)
    for key, label in STAGE_DEFS
] + [
    # Обязательные служебные колонки
    ("row_type", "Тип строки", "Служебное", 22, True),
    ("row_id", "Хэш / ID строки", "Служебное", 20, True),
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

# Текстовые Да/Нет столбцы — у строк категорий остаются пустыми, снабжены DataValidation
STAGE_TEXT_KEYS: tuple = (
    "is_in_plan", "in_work", "purchase_done", "protocol_signed",
    "contracted", "ordered_flag", "delivered", "paid_marked", "paid_confirmed",
    "active",
)
STAGE_AMOUNT_KEYS: tuple = tuple(f"{k}_amt" for k, _ in STAGE_DEFS)
# Служебная колонка-идентификатор — никогда не показывается в окне выбора
# столбцов (columns_catalog), но всегда пишется в файл (см. resolve_selected_
# keys always= ниже) и читается обратно загрузкой
# (app/services/feo_roundtrip_import/parse.py).
HIDDEN_CATALOG_KEYS: set = {"row_id"}


def columns_catalog() -> list[dict]:
    return [c for c in _columns_catalog(FEO_EXPORT_COLUMNS) if c["key"] not in HIDDEN_CATALOG_KEYS]


def resolve_selected_keys(columns: Optional[str]) -> list:
    return _resolve_selected_keys(FEO_EXPORT_COLUMNS, columns, always=("name", "row_type", "row_id"))


def headers_and_widths(selected_keys: list) -> tuple:
    return _headers_and_widths(_BY_KEY, selected_keys)


def column_index(selected_keys: list, key: str) -> Optional[int]:
    return _column_index(selected_keys, key)
