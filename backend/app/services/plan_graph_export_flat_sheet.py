"""plan_graph_export_flat_sheet.py — лист «План закупок (по порядку)»
(владелец 08.10.2026): одна строка на каждую фактическую позицию закупки
субсидии (включая закупки прямо на статье и закупки без категории ФЭО), БЕЗ
строк направлений/типов/статей и без группировки по дереву — отсортировано
по № закупки, затем по id закупки. Направление/тип/наименование заполнены в
каждой строке (для фильтра). В конце — плановые позиции без закупок (статус
«Не начато», с бюджетом), по порядку дерева. Номер в «№» — тот же «N.k», что
на листе «План закупок (по направлениям)» (plan_graph_export_xlsx.py) — обе
выгрузки читают строки из ОДНОГО сбора (app.services.plan_graph_export_rows
.collect_plan_graph_rows, ПРАВИЛО №5 — второй проход по дереву здесь не
заводится).

Часть B (владелец 08.10.2026): строка 1 — «Итого всего» (подпись + =SUM по
всем денежным столбцам, кроме TOP_SUMMARY_EXCLUDED_KEYS), строка 2 — «Итого
по фильтру» (=SUBTOTAL(109,...)) — через общую app.services.
plan_graph_export_rows.write_flat_top_summary_rows (лист НЕ иерархический —
каждая строка самодостаточна, плановый SUM тут корректен). Шапка — строка 3,
данные — с 4-й."""
from __future__ import annotations

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    openpyxl = None

from app.services.plan_graph_export_columns import MONEY_COL_KEYS, TOP_SUMMARY_EXCLUDED_KEYS, headers_and_widths
from app.services.plan_graph_export_rows import collect_plan_graph_rows, write_flat_top_summary_rows
from app.utils.xlsx_row_height import apply_row_heights

SHEET_NAME = "План закупок (по порядку)"
HEADER_ROW = 3
DATA_FIRST_ROW = 4


def write_flat_plan_graph_sheet(wb, data: dict, selected_keys: list, base_url: str, title: str = "") -> None:
    """Строит лист `SHEET_NAME` в книге `wb` (добавляется в конец книги —
    порядок листов определяет вызывающий роутер порядком вызовов)."""
    rows_info = collect_plan_graph_rows(data)

    HEADER_FILL  = PatternFill("solid", fgColor="1E3A5F")
    HEADER_FONT  = Font(color="FFFFFF", bold=True, size=9)
    ITEM_FONT    = Font(size=9)
    EMPTY_FONT   = Font(size=9, italic=True, color="6B7280")
    CENTER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT_ALIGN   = Alignment(horizontal="left", vertical="center", wrap_text=True)
    RIGHT_ALIGN  = Alignment(horizontal="right", vertical="center", wrap_text=True)
    THIN_BORDER  = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )
    LINK_FONT = Font(size=8, italic=True, color="2563EB", underline="single")
    NUM_FMT = "#,##0.00"

    ws = wb.create_sheet(SHEET_NAME)
    HEADERS, COL_WIDTHS = headers_and_widths(selected_keys)

    # "Бюджет ФЭО" тоже без верхних формул на этом листе (владелец 09.10.2026):
    # здесь он есть только у "хвостовых" позиций без закупок — сумма по
    # столбцу вводит в заблуждение (это не бюджет субсидии).
    money_col_indices = [
        ci for ci, key in enumerate(selected_keys, 1)
        if key in MONEY_COL_KEYS and key not in TOP_SUMMARY_EXCLUDED_KEYS and key != "feo_budget"
    ]
    write_flat_top_summary_rows(
        ws, money_col_indices,
        title=title or f"{SHEET_NAME} — итого всего", data_first_row=DATA_FIRST_ROW,
    )

    for ci, (header, width) in enumerate(zip(HEADERS, COL_WIDTHS), 1):
        cell = ws.cell(row=HEADER_ROW, column=ci, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = f"A{DATA_FIRST_ROW}"

    row_num = DATA_FIRST_ROW

    def _write(values: dict, font) -> int:
        nonlocal row_num
        idx = row_num
        for ci, key in enumerate(selected_keys, 1):
            val = values.get(key, "")
            cell = ws.cell(row=idx, column=ci, value=val)
            cell.font = font
            cell.border = THIN_BORDER
            is_money = key in MONEY_COL_KEYS
            cell.alignment = RIGHT_ALIGN if (is_money or key in ("qty", "pct", "num")) else LEFT_ALIGN
            if is_money and isinstance(val, (int, float)):
                cell.number_format = NUM_FMT
        row_num += 1
        return idx

    # «План (плановые позиции)» (владелец 09.10.2026, замечание 3б, сверка
    # проверка на проде ФАДМ 2026_2) — на этом листе у позиции С закупками
    # нет своей отдельной строки (только её закупки, см. ниже); план пишется
    # РОВНО на первую (по сортировке) строку позиции — иначе задвоится при
    # простом SUM по столбцу (владелец: «выбери и опиши решение»). Значение —
    # item_plan_map (ПРАВИЛО №6: та же контрибьюция, что суммирует дерево
    # ФЭО, см. docstring gather_live_plan_graph_data; НЕ голое item.amount).
    item_plan_map = data.get("item_plan_map") or {}
    # Фолбэк на item.amount (только если item_plan_map не несёт эту позицию —
    # в реальных данных gather_live_plan_graph_data заполняет её для КАЖДОЙ
    # активной позиции; фолбэк нужен только старым синтетическим данным в
    # тестах, не меняет поведение на проде).
    item_by_id: dict = {
        item.id: item
        for items in (data.get("items_by_cat") or {}).values()
        for item in items
    }

    # Все фактические строки (по плановым позициям + прямо на статье + без
    # категории ФЭО), в ОДНОМ списке, отсортированные по № закупки → id закупки.
    all_rows: list = []
    for item_id, rows in rows_info["fact_rows_by_item"].items():
        if rows:
            if item_id in item_plan_map:
                rows[0]["plan_amount"] = round(item_plan_map[item_id], 2)
            elif item_id in item_by_id:
                rows[0]["plan_amount"] = round(float(item_by_id[item_id].amount or 0), 2)
        all_rows.extend(rows)
    for rows in rows_info["fact_rows_by_cat"].values():
        all_rows.extend(rows)
    all_rows.extend(rows_info["fact_rows_unlinked"])
    all_rows.sort(key=lambda r: r["_sort_key"])

    docs_idx = selected_keys.index("docs") + 1 if "docs" in selected_keys else None
    for row in all_rows:
        row_idx = _write(row, ITEM_FONT)
        pid = row.get("_purchase_id")
        if pid and docs_idx is not None:
            cell = ws.cell(row=row_idx, column=docs_idx, value="Открыть")
            cell.hyperlink = f"{base_url}/orders/{pid}"
            cell.font = LINK_FONT

    # «Товар / услуга» плановой позиции (владелец 08.10.2026, замечание 1) —
    # уже посчитано централизовано gather_live_plan_graph_data (ПРАВИЛО №6).
    item_kind_map = data.get("item_kind_map") or {}
    # «План. месяц платежа» позиций без закупок (владелец 09.10.2026, п.2) —
    # item_plan_month_map (см. plan_graph_export_data.item_planned_month).
    item_plan_month_map = data.get("item_plan_month_map") or {}

    # Хвост — плановые позиции без закупок, по порядку дерева (владелец:
    # «в конце — позиции без закупок»).
    for info in rows_info["items_without_purchase"]:
        item = info["item"]
        feo_budget = float(item.amount or 0)
        plan_contribution = item_plan_map.get(item.id, feo_budget)
        values = {
            "level": "Позиция",
            "num": str(info["seq"]), "direction": info["direction"], "type": info["type"],
            "name": item.name, "unit": item.unit or "", "qty": float(item.quantity or 0),
            "item_kind": item_kind_map.get(item.id, ""),
            "planned_payment_month": item_plan_month_map.get(item.id, ""),
            # «Бюджет ФЭО» — только в строках статей (владелец 09.10.2026,
            # замечание 3а), здесь (строка позиции) пусто; план самой позиции —
            # "plan_amount" (единственная её строка на листе — без закупок,
            # повторения нет); «Остаток» — против собственного бюджета
            # позиции (как и раньше, см. тот же комментарий в xlsx.py).
            "plan_amount": round(plan_contribution, 2), "residual": round(feo_budget, 2),
            "status": "Не начато",
        }
        _write(values, EMPTY_FONT)

    last_row = row_num - 1
    last_col_letter = ws.cell(row=HEADER_ROW, column=len(HEADERS)).column_letter
    ws.auto_filter.ref = f"A{HEADER_ROW}:{last_col_letter}{max(last_row, HEADER_ROW)}"
    apply_row_heights(ws, range(1, last_row + 1))
