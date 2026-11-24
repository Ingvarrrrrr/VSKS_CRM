"""Item-import file-parsing helpers (таблицы HTML/PDF/DOCX и детектор УПД).

QR/OCR изображений вынесены в items_import_qr_ocr.py, а прямое чтение Excel —
в items_import_excel.py (Правило №5, < 500 строк) и реэкспортируются отсюда
для сохранения обратной совместимости всех точек импорта.
"""
import logging
import re
from decimal import Decimal
from io import BytesIO

from app.services.item_amounts import line_total
from app.services.items_import_excel import (  # noqa: F401
    _looks_mojibake,
    _read_excel_rows,
    _smart_import_xlsx_direct,
)
from app.services.items_import_qr_ocr import (  # noqa: F401
    _smart_import_image_ocr,
    _try_decode_qr,
)
from app.utils.numbers import to_decimal

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

try:
    import pdfplumber as _pdfplumber
except ImportError:
    _pdfplumber = None

try:
    from docx import Document as _DocxDocument
except ImportError:
    _DocxDocument = None

try:
    from bs4 import BeautifulSoup as _BeautifulSoup
except ImportError:
    _BeautifulSoup = None

logger = logging.getLogger(__name__)


def _ocr_pdf_to_rows(content: bytes) -> tuple[list, str | None]:
    """Thin delegating wrapper around app.utils.pdf_ocr.ocr_pdf_to_rows."""
    from app.utils.pdf_ocr import ocr_pdf_to_rows as _impl
    return _impl(content)


def _ocrmypdf_then_extract_tables(content: bytes) -> list[list[list[str]]]:
    """Thin delegating wrapper around app.utils.pdf_ocr.ocrmypdf_then_extract_tables."""
    from app.utils.pdf_ocr import ocrmypdf_then_extract_tables as _impl
    return _impl(content)


def _extract_html_tables(content: bytes, filename: str = "doc.html") -> list[list[list[str]]]:
    """Single source of truth for HTML→tables extraction (/items/import-preview & /items/import-mapped)."""
    raw_tables: list[list[list[str]]] = []
    try:
        from app.utils.document_to_markdown import file_to_markdown, parse_markdown_tables
        md_text = file_to_markdown(content, filename)
        raw_tables = parse_markdown_tables(md_text)
    except Exception as e:
        logger.warning("markitdown HTML parse failed: %s", e)
        raw_tables = []
    if not raw_tables:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            for tbl in soup.find_all('table'):
                rows = []
                for tr in tbl.find_all('tr'):
                    cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                    if cells:
                        rows.append(cells)
                if rows:
                    raw_tables.append(rows)
        except Exception as e:
            logger.warning("BeautifulSoup HTML fallback failed: %s", e)
    return raw_tables


def _legacy_extract_tables(content: bytes, filename: str, file_type: str) -> list[list[list[str]]]:
    """Fallback table extraction using original libraries (pdfplumber, python-docx, openpyxl)."""
    raw_tables: list[list[list[str]]] = []
    if file_type == "excel":
        if load_workbook:
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            rows = [[str(c) if c is not None else "" for c in row] for row in ws.iter_rows(values_only=True)]
            if rows:
                raw_tables.append(rows)
    elif file_type == "pdf":
        if _pdfplumber:
            with _pdfplumber.open(BytesIO(content)) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables() or []
                    for tbl in tables:
                        if tbl:
                            raw_tables.append([[str(c) if c is not None else "" for c in row] for row in tbl])
        _ocr_pages: list[int] | None = None
        if not raw_tables:
            try:
                from app.utils.pdf_classify import inspect_pdf as _inspect_pdf_classify
                _insp = _inspect_pdf_classify(content)
                if _insp.ok:
                    _ocr_pages = _insp.ocr_pages or None
            except Exception as e:
                logger.warning("_legacy_extract_tables: pdf classification unavailable: %s", e)
        if not raw_tables:
            ocr_tables = _ocrmypdf_then_extract_tables(content)
            if ocr_tables:
                raw_tables.extend(ocr_tables)
        if not raw_tables:
            from app.utils.pdf_ocr import ocr_pdf_to_rows_enhanced
            ocr_rows, _ = ocr_pdf_to_rows_enhanced(content, pages=_ocr_pages)
            if ocr_rows:
                raw_tables.append(ocr_rows)
    elif file_type == "docx":
        if _DocxDocument:
            doc = _DocxDocument(BytesIO(content))
            for table in doc.tables:
                rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
                if rows:
                    raw_tables.append(rows)
    elif file_type == "html":
        if _BeautifulSoup:
            soup = _BeautifulSoup(content, 'html.parser')
            for tbl in soup.find_all('table'):
                rows = []
                for tr in tbl.find_all('tr'):
                    cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                    if cells:
                        rows.append(cells)
                if rows:
                    raw_tables.append(rows)
        else:
            logger.warning("BeautifulSoup not installed, skipping HTML fallback parsing")
    return raw_tables


def _detect_upd_layout(row: list[str]) -> dict | None:
    """Detect УПД numeric label row (Постановление № 1137; '1а' приоритетнее '1б' по реальным УПД)."""
    labels = {'1а', '1б', '2', '2а', '3', '4', '5', '9'}
    found = {}
    for i, h in enumerate(row):
        h_s = h.strip().lower().replace(' ', '')
        if h_s in labels or h_s in {'1', '6', '7', '8', '10', '10а', '11', '12', '12а', '13'}:
            found[h_s] = i
    if len(labels & set(found.keys())) < 4:
        return None
    col: dict = {}
    if '1а' in found:
        col['item_name'] = found['1а']
    elif '1б' in found:
        col['item_name'] = found['1б']
    if '3' in found:
        col['quantity'] = found['3']
    if '4' in found:
        col['unit_price'] = found['4']
    if '5' in found:
        col['total_wo_tax'] = found['5']
    if '9' in found:
        col['total_price'] = found['9']
    elif '5' in found:
        col['total_price'] = found['5']
    if '2а' in found:
        col['unit'] = found['2а']
    if '2' in found:
        col['unit_code'] = found['2']
        col.setdefault('unit', found['2'])
    if '7' in found:
        col['vat_rate'] = found['7']
    if '8' in found:
        col['vat_amount'] = found['8']
    return col if 'item_name' in col else None


UPD_OKEI_UNITS = {
    '796': 'шт', '006': 'м', '868': 'компл.', '112': 'л', '166': 'кг',
    '055': 'м2', '113': 'м3', '245': 'усл.ед.', '876': 'усл.ед.',
    '704': 'компл.', '163': 'г', '350': 'упак.', '778': 'компл.',
}


def _okei_to_unit(code: str | None) -> str | None:
    """Код ОКЕИ (напр. '796') → условное обозначение ('шт')."""
    if not code:
        return None
    c = str(code).strip()
    if not c or c in ('--', '-', '—'):
        return None
    c_norm = c.lstrip('0') or '0'
    return UPD_OKEI_UNITS.get(c) or UPD_OKEI_UNITS.get(c_norm) or UPD_OKEI_UNITS.get(c_norm.zfill(3))


_UPD_CORRUPTED_CELL_RE = re.compile(r'[0-9][а-яА-Я]|[а-яА-Я][0-9]')


def find_upd_code_row(rows: list[list], search_limit: int = 30) -> tuple[int, dict] | None:
    """Ищет строку кодов УПД (1|1а|1б|2|2а|3|4|5|9) в первых `search_limit` строках таблицы."""
    best_idx = -1
    best_col: dict = {}
    for r_idx, row in enumerate(rows[:search_limit]):
        row_str = [str(c) if c is not None else "" for c in row]
        col = _detect_upd_layout(row_str)
        if col and len(col) > len(best_col):
            best_col = col
            best_idx = r_idx
    if best_idx < 0:
        return None
    return best_idx, best_col


def parse_upd_table(rows: list[list], code_row_idx: int, col: dict) -> dict:
    """Разбирает позиции УПД из строк после строки кодов до «Всего к оплате»."""
    items: list[dict] = []
    warnings: list[dict] = []
    _to_dec = to_decimal

    def _cell(row: list[str], field: str) -> str | None:
        idx = col.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        if v is None:
            return None
        s = str(v).strip()
        return s if s and s not in ('--', '-', '—') else None

    total_row_value: Decimal | None = None
    computed_sum = Decimal('0')
    row_num = code_row_idx + 1
    for raw_row in rows[code_row_idx + 1:]:
        row_num += 1
        row = [str(c) if c is not None else "" for c in raw_row]
        joined = " ".join(row).lower()
        if 'всего к оплате' in joined or 'итого к оплате' in joined:
            total_cell = _cell(row, 'total_price')
            total_row_value = _to_dec(total_cell) if total_cell else None
            break
        name = " ".join((_cell(row, 'item_name') or "").split())
        if not name:
            continue
        quantity = _to_dec(_cell(row, 'quantity'))
        unit_price = _to_dec(_cell(row, 'unit_price'))
        vat_rate_raw = _cell(row, 'vat_rate')
        unit_val = _cell(row, 'unit') or _okei_to_unit(_cell(row, 'unit_code'))
        unit = unit_val or 'шт'

        total_cell_raw = _cell(row, 'total_price')
        corrupted = bool(total_cell_raw and _UPD_CORRUPTED_CELL_RE.search(total_cell_raw))
        total_price = None if corrupted else _to_dec(total_cell_raw)
        if total_price is None and unit_price is not None and quantity is not None:
            total_price = line_total(quantity, unit_price, rate=vat_rate_raw, on_top=True)
            if corrupted:
                warnings.append({
                    "row": row_num, "item_name": name,
                    "code": "upd_corrupted_cell",
                    "message": (
                        f"Строка {row_num} «{name}»: ячейка суммы повреждена при извлечении "
                        f"(«{total_cell_raw}») — сумма пересчитана как кол-во × цена × (1 + ставка)."
                    ),
                })
        if total_price is not None:
            computed_sum += total_price

        items.append({
            "row": row_num,
            "item_name": name,
            "item_type": "товар",
            "quantity": float(quantity) if quantity is not None else None,
            "unit": unit,
            "unit_raw": unit_val,
            "unit_price": float(unit_price) if unit_price is not None else None,
            "total_price": float(total_price) if total_price is not None else None,
            "vat_rate": vat_rate_raw,
        })

    if total_row_value is not None and items:
        diff = abs(computed_sum - total_row_value)
        if diff > Decimal('0.05'):
            warnings.append({
                "row": None, "item_name": None,
                "code": "upd_total_mismatch",
                "message": (
                    f"Сумма по строкам ({computed_sum}) не совпадает со строкой "
                    f"«Всего к оплате» в документе ({total_row_value}), расхождение {diff}."
                ),
            })

    return {
        "items": items,
        "warnings": warnings,
        "columns_found": list(col.keys()),
    }


def build_upd_sheet_extra(all_rows: list[list]) -> dict | None:
    """Если `all_rows` распознаются как УПД — вернуть overrides для /items/import-preview."""
    found = find_upd_code_row(all_rows)
    if not found:
        return None
    code_row_idx, col = found
    parsed = parse_upd_table(all_rows, code_row_idx, col)
    if not parsed["items"]:
        return None
    field_map = {
        "item_name": col.get("item_name"),
        "quantity": col.get("quantity"),
        "unit_price": col.get("unit_price"),
        "unit": col.get("unit"),
        "total_price": col.get("total_price"),
        "vat_rate": col.get("vat_rate"),
    }
    auto_mapping = {k: v for k, v in field_map.items() if v is not None}
    data_rows = all_rows[code_row_idx + 1:code_row_idx + 6]
    sample = [[str(c) if c is not None else "" for c in r] for r in data_rows]
    return {
        "is_upd": True,
        "header_row_offset": code_row_idx,
        "auto_mapping": auto_mapping,
        "preview": parsed["items"],
        "warnings": parsed["warnings"],
        "sample": sample,
    }


def _legacy_detect_best_table(raw_tables: list[list[list[str]]]) -> tuple:
    """Fallback column detection on raw tables: (best_table, best_col, best_header_row, is_upd)."""
    def _detect_columns_legacy(header_row: list[str]) -> dict:
        col: dict = {}
        for i, h in enumerate(header_row):
            h_s = h.strip().lower()
            if 'наименование товара' in h_s or 'описание выполненных' in h_s or 'описание оказанных' in h_s:
                col.setdefault("item_name", i)
            elif any(x in h_s for x in (
                "наименован", "назван", "name", "товар", "предмет", "описан",
                "услуг", "работ", "маршрут", "направлен", "рейс", "билет",
            )):
                col.setdefault("item_name", i)
            elif any(x in h_s for x in ("тип", "type", "вид")):
                col.setdefault("item_type", i)
            elif any(x in h_s for x in ("количество (объем)", "кол-во", "количеств", "qty", "quantity")) or h_s.startswith("кол"):
                col.setdefault("quantity", i)
            elif "ед. изм" in h_s or "единиц" in h_s or "ед.изм" in h_s or h_s == "ед." or h_s == "unit":
                col.setdefault("unit", i)
            elif any(x in h_s for x in (
                "цена", "тариф", "price", "стоимость", "сумма билет", "цена билет",
            )):
                col.setdefault("unit_price", i)
            elif any(x in h_s for x in ("ставка ндс", "налоговая ставка", "% ндс", "ндс %", "vat rate")):
                col.setdefault("vat_rate", i)
            elif any(x in h_s for x in ("сумма ндс", "vat amount")):
                col.setdefault("vat_amount", i)
            elif "с налогом" in h_s and "всего" in h_s:
                col["total_price"] = i
            elif any(x in h_s for x in ("к оплате", "сумма с налогом", "итого с ндс")):
                col["total_price"] = i
            elif "total_price" not in col and any(x in h_s for x in ("сумма", "итог", "total", "amount", "всего", "стоимость")):
                col["total_price"] = i
        return col

    best_table: list[list[str]] = []
    best_col: dict = {}
    best_header_row = 0
    for table in raw_tables:
        for r_idx, row in enumerate(table[:8]):
            upd_col = _detect_upd_layout(row)
            if upd_col and len(upd_col) > len(best_col):
                best_col = upd_col
                best_table = table
                best_header_row = r_idx
    if best_col:
        return best_table, best_col, best_header_row, True
    for table in raw_tables:
        for r_idx, row in enumerate(table[:6]):
            col = _detect_columns_legacy(row)
            if "item_name" in col and len(col) > len(best_col):
                best_col = col
                best_table = table
                best_header_row = r_idx
    return best_table, best_col, best_header_row, False
