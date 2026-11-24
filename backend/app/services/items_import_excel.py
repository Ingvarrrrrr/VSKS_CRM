"""Прямое чтение XLSX/XLS (включая BIFF8 cp1251 mojibake) для импорта позиций.

Вынесено из items_import_parsing.py по Правилу №5 (< 500 строк на файл).
"""
from __future__ import annotations

import re as _re
from io import BytesIO

from app.services.item_amounts import line_total
from app.services.qty_price_check import check_qty_price_sum
from app.utils.numbers import to_decimal

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None


def _looks_mojibake(wb) -> bool:
    """Эвристика: ≥50% строковых ячеек в первом листе состоят из latin-1 supplement (0xC0..0xFF) или U+FFFD."""
    try:
        ws = wb.sheet_by_index(0)
    except Exception:
        return False
    total = 0
    bad = 0
    for r in range(min(ws.nrows, 20)):
        for v in ws.row_values(r):
            if not isinstance(v, str) or len(v.strip()) < 2:
                continue
            total += 1
            s = v.strip()
            if '\ufffd' in s:
                bad += 1
                continue
            latin_supp = sum(1 for ch in s if 0x00C0 <= ord(ch) <= 0x00FF)
            if latin_supp >= max(2, len(s) // 2):
                bad += 1
    return total > 0 and bad / total >= 0.5


def _read_excel_rows(content: bytes, fname: str) -> list[list[list]]:
    """Универсальное чтение Excel: list[sheets] → list[rows] → list[cells] (.xlsx + .xls BIFF8)."""
    is_xls = (fname or '').lower().endswith('.xls') or content[:4] == b'\xd0\xcf\x11\xe0'
    if is_xls:
        import xlrd as _xlrd
        wb = _xlrd.open_workbook(file_contents=content, formatting_info=False)
        if _looks_mojibake(wb):
            wb = _xlrd.open_workbook(file_contents=content, encoding_override='cp1251')
        sheets = []
        for si in range(wb.nsheets):
            ws = wb.sheet_by_index(si)
            sheets.append([list(ws.row_values(r)) for r in range(ws.nrows)])
        return sheets
    if load_workbook is None:
        raise RuntimeError("openpyxl не установлен")
    wb = load_workbook(BytesIO(content), read_only=False, data_only=True)
    return [[list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets]


def _smart_import_xlsx_direct(content: bytes, fname: str = '') -> tuple[list[dict], list[str], list[dict]]:
    """Direct XLSX/XLS parser — устойчив к опечаткам в заголовке, УПД-раскладке и merged headers."""
    from app.services.items_import_parsing import find_upd_code_row, parse_upd_table

    # 'unit_price' обязан идти раньше 'unit' («Цена за единицу» содержит подстроку «единиц»).
    header_patterns = {
        'item_name': ['наимен', 'товар', 'позици', 'описан', 'материал', 'предмет'],
        'item_type': ['тип', 'вид'],
        'quantity': ['колич', 'кол-во', 'кол.', 'кол ', 'кол.во', 'qty'],
        'unit_price': ['цена за ед', 'цена ед', 'цена/ед', 'цена', 'unit price', 'стоимость ед'],
        'unit': ['ед.из', 'ед. изм', 'едизм', 'единиц', 'unit'],
        'total_price': ['сумма', 'итого', 'стоимость', 'total'],
        'description': ['характерист', 'тз', 'спецификац', 'specification'],
    }

    try:
        sheets = _read_excel_rows(content, fname)
    except Exception:
        return [], [], []
    all_rows: list[list] = [r for sh in sheets for r in sh]

    _upd = find_upd_code_row(all_rows)
    if _upd:
        _code_row_idx, _col = _upd
        _res = parse_upd_table(all_rows, _code_row_idx, _col)
        if _res["items"]:
            return _res["items"], _res["columns_found"], _res["warnings"]

    def _classify_header(row: list) -> dict:
        mapping: dict[int, str] = {}
        for idx, cell in enumerate(row):
            if cell is None:
                continue
            text = str(cell).lower().strip()
            if not text:
                continue
            for field, patterns in header_patterns.items():
                if any(p in text for p in patterns):
                    if field not in mapping.values():
                        mapping[idx] = field
                    break
        return mapping

    best_idx = -1
    best_map: dict[int, str] = {}
    best_score = 0
    for i, row in enumerate(all_rows):
        mapping = _classify_header(row)
        if 'item_name' not in mapping.values() or len(mapping) < 2:
            continue
        score = len(mapping)
        if score > best_score:
            best_score = score
            best_idx = i
            best_map = mapping

    if best_idx == -1:
        return [], [], []

    field_to_idx = {v: k for k, v in best_map.items()}
    columns_found = list(field_to_idx.keys())
    _to_dec = to_decimal

    def _get_cell(row: list, field: str):
        idx = field_to_idx.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        return v if v not in (None, '') else None

    type_map = {
        'товар': 'товар', 'товары': 'товар',
        'услуга': 'услуга', 'услуги': 'услуга',
        'работа': 'работа', 'работы': 'работа',
    }

    preview: list[dict] = []
    warnings: list[dict] = []
    for i, row in enumerate(all_rows[best_idx + 1:]):
        row_num = best_idx + 2 + i
        name_val = _get_cell(row, 'item_name')
        if name_val is None:
            continue
        name = _re.sub(r'\s+', ' ', str(name_val).strip().replace('\n', ' ').replace('\r', ' '))
        if not name:
            continue
        qty = _to_dec(_get_cell(row, 'quantity'))
        unit_price = _to_dec(_get_cell(row, 'unit_price'))
        total_price = _to_dec(_get_cell(row, 'total_price'))
        if qty is None and unit_price is None and total_price is None:
            continue
        _mismatch = check_qty_price_sum(row_num, name, qty, unit_price, total_price)
        if _mismatch:
            warnings.append(_mismatch)
        if unit_price is None and total_price is not None and qty:
            try:
                unit_price = total_price / qty
            except Exception:
                pass
        if total_price is None and unit_price is not None and qty:
            total_price = line_total(qty, unit_price)
        unit_val = _get_cell(row, 'unit')
        unit_raw = str(unit_val).strip() if unit_val else None
        unit = unit_raw or 'шт'
        type_val = _get_cell(row, 'item_type')
        item_type = type_map.get(str(type_val).lower().strip() if type_val else '', 'товар')
        desc_val = _get_cell(row, 'description')
        description = None
        if desc_val is not None:
            description = _re.sub(r'\n+', '\n', str(desc_val).strip().replace('\r', ' ')).strip() or None
        preview.append({
            'row': row_num,
            'item_name': name,
            'item_type': item_type,
            'quantity': float(qty) if qty else None,
            'unit': unit,
            'unit_raw': unit_raw,
            'unit_price': float(unit_price) if unit_price else None,
            'total_price': float(total_price) if total_price else None,
            'description': description,
        })
    return preview, columns_found, warnings
