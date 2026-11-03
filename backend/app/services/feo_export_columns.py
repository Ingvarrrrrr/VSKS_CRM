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

# Шесть стадий шкалы (app.services.plan_item_stage.STAGE_*) — подписи те же,
# что frontend/src/constants/planStageScale.ts (ПРАВИЛО №6), плюс «Товар
# поставлен» (не строчка шкалы `stage`, а отдельный признак segments[].delivered,
# см. докстринг plan_item_stage.py).
STAGE_DEFS: list[tuple] = [
    ("in_work", "Закупка в работе"),
    ("contracted", "Договор заключён"),
    ("ordered_flag", "Товар заказан"),
    ("delivered", "Товар поставлен"),
    ("paid_marked", "Оплачено по отметке"),
    ("paid_confirmed", "Подтверждено выпиской"),
]

# (key, label, group, ширина, default)
#
# ПОЛЯ МОДЕЛИ (задача владельца 20.10.2026, часть «колонки цены/количества по
# плану»): у FeoPlannedItem ДВА независимых комплекта чисел (см. докстринг
# feo_quantity/feo_unit_price/feo_amount в app.models.feo_planned_item) —
# «по ФЭО» (feo_quantity/feo_unit_price/feo_amount) и «план»
# (quantity/unit_price/amount). Единица измерения — ОДНО общее поле `unit`
# (отдельного feo_unit/plan_unit у позиции в модели нет), поэтому колонка
# «Ед.» одна на оба количества. feo_qty/feo_unit ниже default=True (были
# выключены по умолчанию) — владелец просил видеть количество по ФЭО сразу.
FEO_EXPORT_COLUMNS: list[tuple] = [
    ("name", "Наименование", "Основное", 45, True),
    ("code", "Код", "Основное", 12, False),
    ("app", "Прил.", "Основное", 10, False),
    ("feo_qty", "Кол-во по ФЭО", "Основное", 12, True),
    ("feo_unit", "Ед.", "Основное", 8, True),
    ("feo_unit_price", "Цена за ед. по ФЭО (₽)", "Основное", 18, True),
    ("feo", "Финансирование по ФЭО (₽)", "Основное", 20, True),
    ("plan_qty", "Кол-во по плану", "Основное", 12, True),
    ("plan_unit_price", "Цена за ед. по плану (₽)", "Основное", 18, True),
    ("plan", "Запланировано (₽)", "Основное", 20, True),
    ("ordered", "Заказано (₽)", "Основное", 18, True),
    ("to_order", "Надо заказать (₽)", "Основное", 18, True),
    ("residual", "Остаток (₽)", "Основное", 18, True),
    ("active", "Активна", "Основное", 10, True),
] + [
    col
    for key, label in STAGE_DEFS
    for col in (
        (key, label, "Стадии", 16, True),
        (f"{key}_amt", f"{label}, ₽", "Стадии", 16, True),
    )
] + [
    # Данные закупки и платежа (задача владельца 03.11.2026: отображение
    # контрагента, ИНН, номера закупки и реквизитов платежа по каждой позиции)
    ("purchase_number", "Номер закупки", "Закупки и платежи", 18, True),
    ("contractor_name", "Контрагент", "Закупки и платежи", 30, True),
    ("contractor_inn", "ИНН контрагента", "Закупки и платежи", 15, True),
    ("payment_doc_number", "Номер платёжного документа", "Закупки и платежи", 22, True),
    ("payment_date", "Дата платежа", "Закупки и платежи", 14, True),
    ("payment_amount", "Сумма платёжного документа (₽)", "Закупки и платежи", 20, True),
    ("payment_purpose", "Назначение платежа", "Закупки и платежи", 40, True),
    ("payment_kbk", "КБК / Код расходов", "Закупки и платежи", 18, True),
    ("payment_status", "Статус платежа", "Закупки и платежи", 16, True),
] + [
    # Обязательная служебная колонка (всегда включена, см.
    # resolve_selected_keys ниже) — нужна формуле «Итого по фильтру» в
    # feo_export_xlsx.py (SUMPRODUCT по SUBTOTAL с исключением строк
    # категорий, чтобы не задваивать суммы — у категорий сами денежные
    # ячейки уже SUM по прямым детям). Значения: «Категория» (есть дети),
    # «Позиция» (плановая позиция), «Категория без позиций» (лист без детей
    # и без плановых позиций — budget/значения заданы литералом).
    ("row_type", "Тип строки", "Служебное", 22, True),
    # Уникальный идентификатор/хэш строки (задача владельца 03.11.2026):
    # «c<id>» категория / «p<id>» плановая позиция / «NEW-<row>» для новых.
    # Расположен в самом конце таблицы, защищён от ручного редактирования.
    ("row_id", "Хэш / ID строки", "Служебное", 18, True),
]

_BY_KEY = {k: (label, group, width) for k, label, group, width, _d in FEO_EXPORT_COLUMNS}
ALL_KEYS: list = [k for k, *_ in FEO_EXPORT_COLUMNS]
DEFAULT_KEYS: list = [k for k, _l, _g, _w, is_default in FEO_EXPORT_COLUMNS if is_default]
MONEY_KEYS: set = {"feo", "plan", "ordered", "to_order", "residual", "feo_unit_price", "plan_unit_price", "payment_amount"} | {f"{k}_amt" for k, _ in STAGE_DEFS}
# Текстовые Да/Частично/Нет столбцы по стадиям — у строк категорий остаются
# пустыми (владелец: «у категорий текстовые стадии — пусто»).
STAGE_TEXT_KEYS: tuple = tuple(k for k, _ in STAGE_DEFS)
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
