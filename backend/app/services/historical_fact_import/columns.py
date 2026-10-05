"""Автоопределение колонок по заголовкам обоих форматов-образцов.

Формат 'columns' (ХО): одна строка заголовков, иерархия — отдельные колонки
«Уровень 2/3/4» + «Плановая позиция», факт — ТРИ колонки подряд, из которых
текстовый заголовок есть только у первой («Факт» на всю тройку кол-во/цена/
сумма — так устроен образец, см. _СМЕТА_ХО_2026_МАО_Статусы.xlsx).

Формат 'sections' (ЛНР): ДВЕ строки заголовка — группа («ПЛАН»/«ФАКТ» и
т.п.) и под-заголовки (кол-во/цена за ед./всего) под группами «ПЛАН»/«ФАКТ»;
«Оплата»/«Законтрактовано»/«Экономия»/«Правильный статус»/«Поставщик» —
одноколоночные группы без отдельного под-заголовка (группа = заголовок).
Иерархия — не в отдельных колонках уровня, а в двух колонках «Наименование
статей затрат» (верхний уровень) + «Подкатегория» (лист), плюс «№ п/п» с
номером раздела у строки верхнего уровня.

ПРАВИЛО №5: этот модуль ТОЛЬКО определяет колонки; разбор строк — rows.py.

Переиспользует services.import_preview_sheets.read_preview_sheets для
листинга листов (ПРАВИЛО №6 — одно место чтения листов Excel).
"""
from __future__ import annotations

from typing import Optional

from app.services.import_preview_sheets import read_preview_sheets, read_full_sheet_rows

# Хинты для detect_header_row/listing — общий словарь слов обоих форматов,
# достаточно широкий, чтобы найти заголовок независимо от формата файла.
_HEADER_HINTS = (
    "уровень", "план", "факт", "оплач", "законтракт", "статус", "поставщик",
    "№ закупки", "наименование", "подкатегория", "количество", "сумма",
    "ед. изм", "товар/услуга",
)

# Канонический заголовок формата 'columns' (как в образце ХО) — используется
# и для разбора (тесты), и для генерации шаблона (template.py), чтобы шаблон
# владельца и наш парсер говорили на одном расположении колонок (ПРАВИЛО №6 —
# один макет, не вторая копия индексов).
TEMPLATE_HEADER: list = [None] * 28
TEMPLATE_HEADER[0] = "Субсидия"
TEMPLATE_HEADER[4] = "Уровень 2 (Направление расходов по ФЭО)"
TEMPLATE_HEADER[5] = "Уровень 3 (Тип расходов по ФЭО)"
TEMPLATE_HEADER[6] = "Уровень 4 (Конкретизированный)"
TEMPLATE_HEADER[7] = "Плановая позиция (папка НЕ создаётся)"
TEMPLATE_HEADER[8] = "Товар/услуга/работа"
TEMPLATE_HEADER[9] = "Комментарий"
TEMPLATE_HEADER[10] = "План 2026"
TEMPLATE_HEADER[14] = "Ед. изм. плана"
TEMPLATE_HEADER[15] = "Плановое количество"
TEMPLATE_HEADER[16] = "Плановая цена за единицу"
TEMPLATE_HEADER[17] = "Сумма плана"
TEMPLATE_HEADER[18] = "Факт"
TEMPLATE_HEADER[21] = "Оплачено "
TEMPLATE_HEADER[22] = "Законтрактовано"
TEMPLATE_HEADER[24] = "Правильный статус"
TEMPLATE_HEADER[25] = "№ Закупки"
TEMPLATE_HEADER[27] = "Поставщик "

FIELDS = (
    "path_l2", "path_l3", "path_l4", "plan_item_name", "item_type", "unit",
    "plan_qty", "plan_price", "plan_amount",
    "fact_qty", "fact_price", "fact_amount",
    "paid", "contracted", "status", "status_raw", "purchase_no", "supplier",
    "comment",
)


def _norm(s) -> str:
    return str(s).strip().lower() if s is not None else ""


def list_sheets(content: bytes, filename: str) -> dict:
    """POST /sheets — {sheets: [{name, rows, header_row_guess}]}."""
    raw = read_preview_sheets(content, filename, _HEADER_HINTS, sample_rows=3)
    return {
        "sheets": [
            {
                "name": s["name"],
                "rows": s.get("total_rows", 0),
                "header_row_guess": s.get("header_row_offset", 0) + 1,  # 1-based для фронта
            }
            for s in raw["sheets"]
        ]
    }


def _col_letter(idx0: int) -> str:
    """0-based индекс колонки → буква Excel (A, B, ..., Z, AA, AB, ...)."""
    n = idx0 + 1
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _score_sections_header(all_rows: list, idx: int) -> bool:
    """Строка idx (0-based) — строка ГРУППОВЫХ заголовков формата 'sections'
    («ПЛАН»/«ФАКТ»/«Оплата»/«Законтрактовано»/«Правильный статус»), а idx+1 —
    строка под-заголовков («Количество, ед.»/«Сумма за ед., руб.»/«Всего, руб»)."""
    if idx + 1 >= len(all_rows):
        return False
    group_row = [_norm(c) for c in all_rows[idx]]
    sub_row = [_norm(c) for c in all_rows[idx + 1]]
    has_plan = any("план" == c or c.startswith("план") for c in group_row)
    has_fact = any(c.strip() == "факт" for c in group_row)
    has_sub = any("количество" in c for c in sub_row) and any("всего" in c for c in sub_row)
    return has_plan and has_fact and has_sub


def detect_format_and_header(content: bytes, filename: str, sheet_name: Optional[str]) -> dict:
    """Возвращает {format, header_row (1-based, строка С ДАННЫМИ начинается
    сразу после), rows: [[...]]} — все строки листа, уже прочитанные один раз
    (используются и для построения columns[], и дальше для rows.py)."""
    all_rows = read_full_sheet_rows(content, filename, sheet_name)
    all_rows = [list(r) for r in all_rows]

    max_scan = min(15, len(all_rows))
    for idx in range(max_scan):
        if _score_sections_header(all_rows, idx):
            return {"format": "sections", "header_row": idx + 2, "rows": all_rows,
                    "group_row": all_rows[idx], "sub_row": all_rows[idx + 1]}

    # Формат 'columns' (ХО) — одна строка заголовка с явными текстами уровней.
    for idx in range(max_scan):
        norm = [_norm(c) for c in all_rows[idx]]
        score = sum(1 for c in norm if c and any(h in c for h in ("уровень", "факт", "оплач", "законтракт", "правильный статус")))
        if score >= 3:
            return {"format": "columns", "header_row": idx + 1, "rows": all_rows, "header": all_rows[idx]}

    # Фолбэк: первая непустая строка — заголовок формата 'columns'.
    for idx in range(max_scan):
        if any(c for c in all_rows[idx]):
            return {"format": "columns", "header_row": idx + 1, "rows": all_rows, "header": all_rows[idx]}
    return {"format": "columns", "header_row": 1, "rows": all_rows, "header": all_rows[0] if all_rows else []}


def _map_columns_format(header: list) -> list:
    """Поколонное сопоставление для формата 'columns' (ХО) — одна строка
    заголовка. Тройка факта (кол-во/цена/сумма) подряд после ячейки «Факт»
    (только первая ячейка тройки содержит текст)."""
    cols = []
    i = 0
    n = len(header)
    while i < n:
        h = _norm(header[i])
        field = None
        if "уровень 2" in h:
            field = "path_l2"
        elif "уровень 3" in h:
            field = "path_l3"
        elif "уровень 4" in h:
            field = "path_l4"
        elif "плановая позиция" in h:
            field = "plan_item_name"
        elif "товар/услуга" in h or "товар / услуга" in h:
            field = "item_type"
        elif "ед. изм. плана" in h or h == "ед. изм.":
            field = "unit"
        elif "плановое количество" in h:
            field = "plan_qty"
        elif "плановая цена" in h:
            field = "plan_price"
        elif "сумма плана" in h:
            field = "plan_amount"
        # Шаблон ФЭО (решение владельца 05.10.2026, app/routers/
        # feo_import_template.py) — необязательный блок «Факт» с явными
        # заголовками «Факт: Количество/Цена/Сумма», В ОТЛИЧИЕ от одноимённой
        # тройки «Факт» (одна ячейка на 3 колонки) образца ХО ниже. Объявлены
        # ПЕРЕД веткой h.strip()=="факт", чтобы "факт: сумма" не пыталась
        # совпасть с ней (там строгое равенство "факт", не совпало бы и так,
        # но порядок рядом — для читаемости).
        elif "факт: количество" in h or "факт количество" in h:
            field = "fact_qty"
        elif "факт: цена" in h or "факт цена" in h:
            field = "fact_price"
        elif "факт: сумма" in h or "факт сумма" in h:
            field = "fact_amount"
        elif h.strip() == "факт":
            cols.append({"index": i, "letter": _col_letter(i), "header": header[i], "field": "fact_qty"})
            if i + 1 < n:
                cols.append({"index": i + 1, "letter": _col_letter(i + 1), "header": header[i + 1], "field": "fact_price"})
            if i + 2 < n:
                cols.append({"index": i + 2, "letter": _col_letter(i + 2), "header": header[i + 2], "field": "fact_amount"})
            i += 3
            continue
        elif "оплач" in h:
            field = "paid"
        elif "законтракт" in h:
            field = "contracted"
        elif "правильный статус" in h:
            field = "status_raw"
        elif h.strip() == "статус":
            field = "status"
        elif "№ закупки" in h:
            field = "purchase_no"
        elif "поставщик" in h:
            field = "supplier"
        elif "коммент" in h:
            field = "comment"
        cols.append({"index": i, "letter": _col_letter(i), "header": header[i], "field": field})
        i += 1
    return cols


def _map_sections_format(group_row: list, sub_row: list) -> list:
    """Поколонное сопоставление для формата 'sections' (ЛНР) — 2 строки
    заголовка (группа + под-заголовок)."""
    cols = []
    n = max(len(group_row), len(sub_row))
    current_group = ""
    for i in range(n):
        g = _norm(group_row[i]) if i < len(group_row) else ""
        s = _norm(sub_row[i]) if i < len(sub_row) else ""
        if g:
            current_group = g
        header_text = group_row[i] if i < len(group_row) and group_row[i] else (sub_row[i] if i < len(sub_row) else None)
        field = None
        if "№ п/п" in s:
            field = None  # номер раздела — не отдельное поле, читается rows.py напрямую
        elif "наименование статей затрат" in s:
            field = "path_l2"
        elif "подкатегория" in s:
            field = "plan_item_name"
        elif "ед. изм" in s:
            field = "unit"
        elif current_group.startswith("план") and "количество" in s:
            field = "plan_qty"
        elif current_group.startswith("план") and "сумма за ед" in s:
            field = "plan_price"
        elif current_group.startswith("план") and "всего" in s:
            field = "plan_amount"
        elif current_group == "факт" and "количество" in s:
            field = "fact_qty"
        elif current_group == "факт" and "сумма за ед" in s:
            field = "fact_price"
        elif current_group == "факт" and "всего" in s:
            field = "fact_amount"
        elif "оплата" in current_group:
            field = "paid"
        elif "законтракт" in current_group:
            field = "contracted"
        elif "правильный статус" in current_group:
            field = "status_raw"
        elif "поставщик" in current_group:
            field = "supplier"
        elif "коммент" in current_group:
            field = "comment"
        cols.append({"index": i, "letter": _col_letter(i), "header": header_text, "field": field})
    return cols


def build_columns(detected: dict) -> list:
    """{format, header_row, header|group_row/sub_row} → columns[] контракта."""
    if detected["format"] == "sections":
        return _map_sections_format(detected["group_row"], detected["sub_row"])
    return _map_columns_format(detected["header"])


def apply_mapping_override(columns: list, mapping: Optional[dict]) -> list:
    """decisions/mapping может переопределить field конкретных колонок по
    индексу (фронт дал пользователю исправить автоопределение)."""
    if not mapping:
        return columns
    overrides = mapping.get("columns") if isinstance(mapping, dict) else None
    if not overrides:
        return columns
    by_index = {int(k): v for k, v in overrides.items()}
    for c in columns:
        if c["index"] in by_index:
            c["field"] = by_index[c["index"]] or None
    return columns
