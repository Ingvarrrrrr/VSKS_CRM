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
    "registry_number", "contract_number", "contract_date",
    "acceptance_doc_number", "acceptance_doc_date",
    "payment_doc_number", "payment_doc_date", "payment_amount", "payment_purpose",
]

# (key, label, group, ширина колонки, default)
PLAN_GRAPH_COLUMNS: list[tuple] = [
    # Служебный столбец «Уровень» (владелец 08.10.2026, часть B — «добавь
    # первым/служебным столбцом») — Направление/Тип/Статья/Позиция/Закупка,
    # нужен для SUMIFS верхней строки «Итого всего» (на иерархическом листе
    # «по направлениям» плановый SUM задваивает группы — см.
    # plan_graph_export_xlsx.py) и для ручного фильтра по уровню строки.
    ("level", "Уровень", "Позиция", 14, True),
    ("num", "№", "Позиция", 6, True),
    # Владелец 08.10.2026: № закупки / № заявки в договоре — отдельные столбцы
    # (значение читается с самой закупки через get_cell_value, ПРАВИЛО №6 —
    # те же ключи purchase_number/order_number, что в экспорте закупок, со
    # своей подписью здесь для контекста плана-графика).
    ("purchase_number", "№ закупки", "Позиция", 10, True),
    ("order_number", "№ заявки в договоре", "Позиция", 14, True),
    ("direction", "Направление расходов", "Позиция", 30, True),
    ("type", "Тип расходов", "Позиция", 25, True),
    ("name", "Наименование", "Позиция", 40, True),
    # «Состав закупки» / «Цена за ед.» — название и цена закупленной позиции
    # (раньше склеивались текстом в name: «    └ Название — цена ₽/ед.»,
    # владелец 08.10.2026 — каждое значение в своём столбце для фильтра).
    ("composition", "Состав закупки", "Позиция", 35, True),
    ("unit_price", "Цена за ед., ₽", "Позиция", 14, True),
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
    ("contractor_inn", _PURCHASE_COLUMNS["contractor_inn"]["label"], "Исполнение", 16, True),
    # «Остаток по договору» (владелец 08.10.2026, часть C) — ЕДИНЫЙ источник
    # app.services.contract_balances.contract_balances, заполняется в
    # строках закупок остатком договора, к которому относится закупка; без
    # договора — пусто. Верхние формулы «Итого всего»/«Итого по фильтру»
    # НЕ ставятся (см. TOP_SUMMARY_EXCLUDED_KEYS) — значение повторяется у
    # каждой заявки одного договора, сумма по столбцу была бы бессмысленна.
    ("contract_balance", "Остаток по договору, ₽", "Исполнение", 18, True),
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
# get_cell_value, см. plan_graph_export_rows.py).
CONTRACT_PAYMENT_COL_KEYS: set = set(_CONTRACT_PAYMENT_KEYS)
# Столбцы, значение которых ВСЕГДА читается с самой закупки через
# purchase_export_cells.get_cell_value — purchase_number/order_number/
# contractor_inn добавлены владельцем 08.10.2026 в набор по умолчанию, но
# механизм получения значения общий с группой «Договор и оплата».
PURCHASE_FIELD_COL_KEYS: set = CONTRACT_PAYMENT_COL_KEYS | {
    "purchase_number", "order_number", "contractor_inn",
}
MONEY_COL_KEYS: set = {
    "feo_budget", "planned", "contract", "ordered", "delivered",
    "paid", "fact_total", "residual", "monthly", "payment_amount", "unit_price",
    "contract_balance",
}
# Денежные столбцы-стадии (владелец 08.10.2026, часть B) — на иерархическом
# листе «по направлениям» это ЕДИНСТВЕННЫЕ денежные столбцы, которые в
# строках направлений/типов/статей/плановых позиций становятся формулой
# =SUBTOTAL(109, ...) по диапазону строк-потомков вместо литерального числа
# (plan_graph_export_xlsx.py); "Бюджет ФЭО"/"Остаток"/"% исполнения" туда не
# входят — остаются значениями на всех уровнях (ФЭО статьи не обязан
# совпадать с суммой позиций).
STAGE_MONEY_COL_KEYS: tuple = ("planned", "contract", "ordered", "delivered", "paid", "fact_total", "monthly")
# Столбцы, которые НЕ включаются в формулы верхних строк «Итого всего»/
# «Итого по фильтру» (владелец 08.10.2026, часть B/C) — их значение
# повторяется у каждой строки одного договора, обычная сумма бессмысленна.
# Владелец 09.10.2026 — "Цена за ед." тоже не суммируется сверху (это цена,
# не сумма; на обоих листах плана).
TOP_SUMMARY_EXCLUDED_KEYS: set = {"contract_balance", "unit_price"}


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
