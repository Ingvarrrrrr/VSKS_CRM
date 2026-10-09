"""Общее чтение листов Excel/XLS/DOCX/PDF для мастеров ручного маппинга
колонок — сначала показать заголовки + примеры строк, потом дать пользователю
подтвердить/поправить соответствие колонок и только тогда импортировать.

Вынесено дословно (без изменения поведения) из
`routers/feo_import_preview.py:44-157` — план dreamy-booping-piglet.md,
задача B, пункт 1 (ПРАВИЛО №6: чтение листов для предпросмотра — ОДНО место,
а не копия на каждый мастер импорта). `feo_import_preview.py` теперь зовёт
`read_preview_sheets()` отсюда со своими hints; импорт товаров
(`routers/products_import.py`) — со своими.

`read_full_sheet_rows()` — второй хелпер, для шага ПОСЛЕ подтверждения
маппинга: читает ВСЕ строки ОДНОГО листа по имени (не `wb.active`/первый
попавшийся — регрессия, которую чинит эта задача, см.
`test_products_import_sheet_select.py`). Логика выбора листа по имени
повторяет уже работающий `routers/feo_import.py` (target_sheet = sheet_name,
если такое имя есть среди листов, иначе первый лист) — не третья копия, а
тот же приём, оформленный как переиспользуемая функция для нового кода.
"""
from io import BytesIO
from typing import Optional

from fastapi import HTTPException

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

try:
    import xlrd as _xlrd
except ImportError:
    _xlrd = None


def detect_header_row(rows: list, hints: tuple, max_scan: int = 20) -> int:
    """Строка-заголовок = строка с максимальным числом узнаваемых имён колонок
    (по ключевым словам `hints`, регистронезависимо, среди первых `max_scan`
    строк листа)."""
    best_score, best_idx = 0, 0
    for ri, row in enumerate(rows[:max_scan]):
        norm = [str(h).strip().lower() if h is not None else "" for h in row]
        score = sum(1 for h in norm if h and any(x in h for x in hints))
        if score > best_score:
            best_score = score
            best_idx = ri
    return best_idx


def read_preview_sheets(content: bytes, filename: str, hints: tuple, sample_rows: int = 5) -> dict:
    """Читает файл целиком, возвращает
    {"sheets": [{name, headers, sample, total_rows, header_row_offset}, ...]}
    по КАЖДОМУ листу/таблице/странице (в зависимости от формата). Заголовки
    определяются `detect_header_row()` с переданными `hints` — свои для
    ФЭО и свои для товаров, поведение мастеров друг с другом не смешивается.
    """
    fname = (filename or "").lower()
    if not fname.endswith((".xlsx", ".xls", ".docx", ".doc", ".pdf")):
        raise HTTPException(400, "Поддерживаются файлы .xlsx, .xls, .docx, .pdf")

    def _detect_hdr(rows):
        return detect_header_row(rows, hints)

    sheets: list = []
    try:
        # ── PDF ──
        if fname.endswith(".pdf"):
            try:
                import pdfplumber
            except ImportError:
                raise HTTPException(500, "pdfplumber не установлен")
            pdf = pdfplumber.open(BytesIO(content))
            all_rows = []
            for page in pdf.pages:
                for t in (page.extract_tables() or []):
                    if t:
                        all_rows.extend([[str(c).strip() if c else "" for c in row] for row in t])
            pdf.close()
            if not all_rows:
                raise HTTPException(400, "Не удалось извлечь таблицы из PDF")
            hdr_idx = _detect_hdr(all_rows)
            headers = [str(h).strip() if h else f"Столбец {j+1}" for j, h in enumerate(all_rows[hdr_idx])]
            data = all_rows[hdr_idx + 1:]
            sample = [[str(c) if c else "" for c in r] for r in data[:sample_rows]]
            return {"sheets": [{"name": "PDF", "headers": headers, "sample": sample, "total_rows": len(data), "header_row_offset": hdr_idx}]}

        # ── DOCX ──
        if fname.endswith((".docx", ".doc")):
            try:
                from docx import Document as _DDoc
            except ImportError:
                raise HTTPException(500, "python-docx не установлен")
            doc = _DDoc(BytesIO(content))
            all_rows = []
            for table in doc.tables:
                for row in table.rows:
                    all_rows.append([cell.text.strip() for cell in row.cells])
            if not all_rows:
                for para in doc.paragraphs:
                    text = para.text.strip()
                    if text:
                        all_rows.append([text])
            if not all_rows:
                raise HTTPException(400, "Не удалось извлечь данные из документа")
            hdr_idx = _detect_hdr(all_rows)
            headers = [str(h).strip() if h else f"Столбец {j+1}" for j, h in enumerate(all_rows[hdr_idx])]
            data = all_rows[hdr_idx + 1:]
            sample = [[str(c) if c else "" for c in r] for r in data[:sample_rows]]
            return {"sheets": [{"name": "Document", "headers": headers, "sample": sample, "total_rows": len(data), "header_row_offset": hdr_idx}]}

        # ── XLS ──
        if fname.endswith(".xls"):
            if _xlrd is None:
                raise HTTPException(500, "xlrd не установлен")
            wb_xls = _xlrd.open_workbook(file_contents=content)
            for sheet_name in wb_xls.sheet_names():
                ws_xls = wb_xls.sheet_by_name(sheet_name)
                all_rows = [list(ws_xls.row_values(i)) for i in range(ws_xls.nrows)]
                if not all_rows:
                    continue
                hdr_idx = _detect_hdr(all_rows)
                hdr_rows = all_rows[hdr_idx:]
                if not hdr_rows:
                    continue
                headers = [str(c).strip() if c else f"Столбец {j+1}" for j, c in enumerate(hdr_rows[0])]
                sample = [[str(c).strip() if c is not None else "" for c in row] for row in hdr_rows[1:min(sample_rows + 1, len(hdr_rows))]]
                sheets.append({"name": sheet_name, "headers": headers, "sample": sample,
                               "total_rows": ws_xls.nrows - hdr_idx - 1, "header_row_offset": hdr_idx})

        # ── XLSX ──
        else:
            if load_workbook is None:
                raise HTTPException(500, "openpyxl не установлен")
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                all_rows = list(ws.iter_rows(values_only=True))
                if not all_rows:
                    continue
                hdr_idx = _detect_hdr(all_rows)
                hdr_rows = all_rows[hdr_idx:]
                if not hdr_rows:
                    continue
                headers = [str(c).strip() if c else f"Столбец {j+1}" for j, c in enumerate(hdr_rows[0])]
                sample = [[str(c).strip() if c is not None else "" for c in row] for row in hdr_rows[1:min(sample_rows + 1, len(hdr_rows))]]
                sheets.append({"name": sheet_name, "headers": headers, "sample": sample,
                               "total_rows": len(all_rows) - hdr_idx - 1, "header_row_offset": hdr_idx})
            wb.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл ({filename}): {e}")

    if not sheets:
        raise HTTPException(400, "Файл не содержит листов с данными")

    return {"sheets": sheets}


def read_full_sheet_rows(
    content: bytes, filename: str, sheet_name: Optional[str], fill_merged: bool = False,
) -> list:
    """Все строки ОДНОГО листа (.xlsx/.xls) по точному имени; если `sheet_name`
    не задан или не найден среди листов файла — берётся первый лист (НЕ
    `wb.active`, который может отличаться от первого листа по порядку —
    см. test_products_import_sheet_select.py).

    `fill_merged=True` (задача импорта факта, план lazy-swimming-hollerith.md,
    п.2) — единственное законное «размножение» значения по строкам: ячейка,
    объединённая в Excel на несколько строк/столбцов, физически хранит
    значение только в своей верхней-левой ячейке (`ws.merged_cells.ranges`),
    openpyxl во всех остальных ячейках диапазона отдаёт `None`. Без этого
    параметра поведение не меняется для существующих вызывающих (products_
    import.py, feo_import.py, historical_fact_import без явного запроса) —
    Правило №6: это НЕ перенос значения из строки выше произвольной ячейки
    (`carry`, который мы убираем из historical_fact_import/rows.py), а просто
    честное прочтение одной и той же Excel-ячейки, которая физически
    занимает несколько строк.
    .xls (xlrd) не поддерживает этот параметр здесь — xlrd отдаёт объединения
    через `ws.merged_cells` отдельным списком диапазонов, но старые .xls-файлы
    исторического импорта факта на практике объединённых ячеек уровня не
    используют; при необходимости это отдельная доработка (не блокирует эту
    задачу)."""
    fname = (filename or "").lower()
    if fname.endswith(".xls"):
        if _xlrd is None:
            raise HTTPException(500, "xlrd не установлен")
        wb = _xlrd.open_workbook(file_contents=content)
        ws_names = wb.sheet_names()
        target = sheet_name if sheet_name in ws_names else ws_names[0]
        ws = wb.sheet_by_name(target)
        return [tuple(ws.row_values(i)) for i in range(ws.nrows)]

    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    # Как и раньше (read_only не указан => False) — `ws.merged_cells.ranges`
    # нужен только в режиме НЕ read_only, поведение для остальных вызывающих
    # (products_import.py, feo_import.py) не меняется: они и раньше грузили
    # книгу без read_only.
    wb = load_workbook(BytesIO(content), data_only=True)
    ws_names = wb.sheetnames
    target = sheet_name if sheet_name in ws_names else ws_names[0]
    ws = wb[target]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    if fill_merged:
        for merged_range in ws.merged_cells.ranges:
            top_value = ws.cell(row=merged_range.min_row, column=merged_range.min_col).value
            if top_value is None:
                continue
            for r in range(merged_range.min_row, merged_range.max_row + 1):
                row_idx = r - 1
                if row_idx >= len(rows):
                    continue
                row = rows[row_idx]
                for c in range(merged_range.min_col, merged_range.max_col + 1):
                    col_idx = c - 1
                    while len(row) <= col_idx:
                        row.append(None)
                    row[col_idx] = top_value
        wb.close()
        return rows
    wb.close()
    return rows
