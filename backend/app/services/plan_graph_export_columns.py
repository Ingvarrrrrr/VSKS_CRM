"""plan_graph_export_columns.py — определение столбцов листа «План закупок»
живого экспорта плана-графика субсидии (Задача D, владелец 07.10.2026).

ПРАВИЛО №6 — тот же приём выбора столбцов, что уже есть у закупок
(app.routers.purchase_export.ALL_EXPORT_COLUMNS/DEFAULT_EXPORT_COLUMNS,
GET /api/purchases/export/columns): форма [{key,label,group}], тот же смысл
query-параметра `columns` (через запятую, неизвестные ключи игнорируются,
пусто/нет → ТОЛЬКО столбцы по умолчанию, см. default=True ниже). Второй
механизм выбора столбцов здесь не заводится — это просто своя таблица ключей
для другого набора столбцов (план-график, не список закупок).

Группа «Договор и оплата» (владелец 07.10.2026 — «при желании видеть к каждой
позиции, к какому платежу она относится, контрагента по этому платежу, номер
договора») — ключи и подписи те же, что в app.services.purchase_export_cells.
ALL_EXPORT_COLUMNS (ПРАВИЛО №6: одна подпись = одно значение, не вторая копия
словаря). Эти столбцы заполняются ТОЛЬКО в под-строках фактических позиций
(есть purchase_id) — см. app.services.plan_graph_export_data и
plan_graph_export_xlsx; в строках направлений/статей/плановых позиций пусто.
Не входят в набор по умолчанию (default=False) — слишком узкоспециальные для
обычного экспорта."""
from __future__ import annotations

from typing import Optional

from app.services.purchase_export_cells import ALL_EXPORT_COLUMNS as _PURCHASE_COLUMNS

# Ключи группы «Договор и оплата» — подписи берутся из _PURCHASE_COLUMNS
# (purchase_export_cells.ALL_EXPORT_COLUMNS), не дублируются здесь.
_CONTRACT_PAYMENT_KEYS: list[str] = [
    "registry_number", "contract_number", "contract_date", "contractor_inn",
    "acceptance_doc_number", "acceptance_doc_date",
    "payment_doc_number", "payment_doc_date", "payment_amount", "payment_purpose",
]

# (key, label, group, ширина колонки, default)
PLAN_GRAPH_COLUMNS: list[tuple] = [
    ("num", "№", "Позиция", 5, True),
    ("direction", "Направление расходов", "Позиция", 30, True),
    ("type", "Тип расходов", "Позиция", 25, True),
    ("name", "Наименование", "Позиция", 40, True),
    ("unit", "Ед.", "Позиция", 8, True),
    ("qty", "Кол-во план", "Позиция", 10, True),
    ("feo_budget", "Бюджет ФЭО, ₽", "Деньги по стадиям", 18, True),
    ("planned", "Запланировано, ₽", "Деньги по стадиям", 18, True),
    ("contract", "Договор, ₽", "Деньги по стадиям", 18, True),
    ("ordered", "Заказано, ₽", "Деньги по стадиям", 18, True),
    ("delivered", "Поставлено, ₽", "Деньги по стадиям", 18, True),
    ("paid", "Оплачено, ₽", "Деньги по стадиям", 18, True),
    ("fact_total", "Фактически (итого), ₽", "Деньги по стадиям", 20, True),
    ("residual", "Остаток, ₽", "Деньги по стадиям", 18, True),
    ("pct", "% исполнения", "Деньги по стадиям", 12, True),
    ("monthly", "Ежемес. (регуляр.) платежи, ₽", "Деньги по стадиям", 22, True),
    ("contractor", "Исполнитель", "Исполнение", 30, True),
    ("status", "Статус", "Исполнение", 15, True),
    ("act", "№ акта", "Исполнение", 16, True),
    ("docs", "Документы", "Исполнение", 14, True),
] + [
    (key, _PURCHASE_COLUMNS[key]["label"], "Договор и оплата",
     22 if key != "payment_purpose" else 30, False)
    for key in _CONTRACT_PAYMENT_KEYS
]

_BY_KEY = {k: (label, group, width) for k, label, group, width, _d in PLAN_GRAPH_COLUMNS}
ALL_KEYS: list = [k for k, *_ in PLAN_GRAPH_COLUMNS]
DEFAULT_KEYS: list = [k for k, _l, _g, _w, is_default in PLAN_GRAPH_COLUMNS if is_default]
# Ключи группы «Договор и оплата» (значение берётся с закупки через
# get_cell_value, см. plan_graph_export_xlsx._purchased_item_values).
CONTRACT_PAYMENT_COL_KEYS: set = set(_CONTRACT_PAYMENT_KEYS)
MONEY_COL_KEYS: set = {
    "feo_budget", "planned", "contract", "ordered", "delivered",
    "paid", "fact_total", "residual", "monthly", "payment_amount",
}


def columns_catalog() -> list[dict]:
    """[{key,label,group,default}] для GET /api/subsidies/plan-graph/export/
    columns — порядок фиксирован (см. PLAN_GRAPH_COLUMNS), совпадает с
    порядком вывода в файле. `default` — входит ли столбец в набор по
    умолчанию (когда ?columns= не передан)."""
    return [
        {"key": k, "label": label, "group": group, "default": is_default}
        for k, label, group, _w, is_default in PLAN_GRAPH_COLUMNS
    ]


def resolve_selected_keys(columns: Optional[str]) -> list:
    """Парсит query-параметр `columns` (через запятую) в список ключей в
    ФИКСИРОВАННОМ порядке PLAN_GRAPH_COLUMNS; неизвестные ключи игнорируются;
    `name` всегда присутствует (владелец — «наименование показываем всегда»).
    Пусто/None → ТОЛЬКО столбцы по умолчанию (DEFAULT_KEYS) — новая группа
    «Договор и оплата» в выгрузку не попадает, пока её не выбрали явно."""
    if not columns:
        return list(DEFAULT_KEYS)
    requested = {c.strip() for c in columns.split(",") if c.strip()}
    requested.add("name")
    selected = [k for k in ALL_KEYS if k in requested]
    return selected or list(DEFAULT_KEYS)


def headers_and_widths(selected_keys: list) -> tuple:
    """(headers, widths) для выбранных ключей, в их порядке."""
    headers = [_BY_KEY[k][0] for k in selected_keys]
    widths = [_BY_KEY[k][2] for k in selected_keys]
    return headers, widths


def column_index(selected_keys: list, key: str) -> Optional[int]:
    """1-based индекс столбца `key` среди выбранных, или None, если столбец
    не выбран (вызывающий код пропускает запись в него — напр. гиперссылка
    «Открыть» в docs, если docs не выбран)."""
    try:
        return selected_keys.index(key) + 1
    except ValueError:
        return None
