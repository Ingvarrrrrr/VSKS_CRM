"""xlsx_row_height.py — подбор высоты строки Excel по тексту самой «высокой»
ячейки этой строки (Задача C экспорта плана-графика, владелец 07.10.2026:
«высота ячеек должна быть по высоте надписи, иначе неудобно растягивать» —
раньше высоты были константами 20/16/28/32, длинные названия статей/
плановых позиций обрезались визуально).

Оценка числа строк переноса — ЭВРИСТИКА (не точный рендер Excel: точная
ширина символа зависит от шрифта/движка), но она единственная во всём
проекте — оба листа экспорта плана-графика (app.services.plan_graph_export_xlsx,
app.services.plan_graph_export_summary_sheet) обязаны звать apply_row_heights
отсюда, а не оценивать высоту по-своему (ПРАВИЛО №6)."""
from __future__ import annotations

from typing import Iterable

# Единица ширины колонки openpyxl ~ ширина одного символа Calibri 11 при
# стандартных настройках Excel; при 9pt (шрифт листов экспорта) в эту же
# единицу умещается чуть больше символов — коэффициент подобран эмпирически.
_CHARS_PER_WIDTH_UNIT = 1.15
_MIN_HEIGHT = 14.0
_LINE_HEIGHT_FACTOR = 1.35
_DEFAULT_COL_WIDTH = 8.43  # Excel-дефолт для колонки без явной ширины


def wrapped_line_count(text, col_width: float, font_size: float = 9.0) -> int:
    """Сколько строк займёт `text` при переносе по словам в столбце шириной
    col_width (единицы openpyxl column width). Явные "\n" внутри текста —
    отдельные абзацы, каждый переносится независимо."""
    if text is None or text == "":
        return 1
    chars_per_line = max(1, int(col_width * _CHARS_PER_WIDTH_UNIT))
    total_lines = 0
    for part in str(text).split("\n"):
        if not part:
            total_lines += 1
            continue
        words = part.split(" ")
        cur_len = 0
        line_count = 1
        for w in words:
            wl = len(w) + 1  # +1 — пробел-разделитель
            if cur_len + wl > chars_per_line and cur_len > 0:
                line_count += 1
                cur_len = wl
            else:
                cur_len += wl
        total_lines += line_count
    return max(1, total_lines)


def row_height_for_row(ws, row_idx: int, *, min_height: float = _MIN_HEIGHT, font_size: float = 9.0) -> float:
    """Высота строки row_idx листа ws по самой «высокой» заполненной ячейке
    (максимум строк переноса среди всех ячеек строки с непустым значением),
    с учётом реальной ширины столбца (ws.column_dimensions[...].width)."""
    max_lines = 1
    for cell in ws[row_idx]:
        value = cell.value
        if value is None or value == "":
            continue
        width = ws.column_dimensions[cell.column_letter].width or _DEFAULT_COL_WIDTH
        lines = wrapped_line_count(value, width, font_size)
        if lines > max_lines:
            max_lines = lines
    line_height = font_size * _LINE_HEIGHT_FACTOR
    return max(min_height, max_lines * line_height + 3)


def apply_row_heights(
    ws, row_range: Iterable[int], *, min_height: float = _MIN_HEIGHT, font_size: float = 9.0,
) -> None:
    """Проставляет ws.row_dimensions[r].height для каждого r из row_range по
    row_height_for_row(...) — единственная точка вызова из обоих модулей
    рендера листов экспорта плана-графика."""
    for r in row_range:
        ws.row_dimensions[r].height = row_height_for_row(ws, r, min_height=min_height, font_size=font_size)
