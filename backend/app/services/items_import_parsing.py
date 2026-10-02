"""Item-import file-parsing helpers — extracted from purchase_items_import.py
(Правило №5, разрезание сессии 2026-09-08).

Pure parsing logic (raw bytes → rows/tables), no HTTP, no DB. Shared across the
split router files: purchase_items_import.py (legacy excel import + preview),
purchase_items_import_mapped.py (column-mapped import) and
purchase_items_import_smart.py (smart import) all call the SAME functions
here — e.g. _extract_html_tables is deliberately the single source of HTML→
tables extraction so that "Таблица N" numbering matches between the preview
endpoint and the mapped-import endpoint (see its docstring below).
"""
import logging
import re
from io import BytesIO
from decimal import Decimal
from fastapi import HTTPException

from app.services.item_amounts import line_total
from app.utils.numbers import to_decimal
from app.services.qty_price_check import check_qty_price_sum

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

# ---------------------------------------------------------------------------
# OCR / legacy table-extraction helpers
# ---------------------------------------------------------------------------

def _ocr_pdf_to_rows(content: bytes) -> tuple[list, str | None]:
    """Thin delegating wrapper around app.utils.pdf_ocr.ocr_pdf_to_rows.

    The real implementation was moved there (Wave 1 of the OCR-classification
    work) so it isn't duplicated between this router and
    app/utils/document_to_markdown.py. Kept here — same name, same signature,
    unpaged — as the module's own OCR-fallback entry point (the two in-module
    call sites that need page-targeted OCR now call
    app.utils.pdf_ocr.ocr_pdf_to_rows_enhanced directly instead, since this
    wrapper's signature has no `pages` argument to pass one through).
    Import is local so importing this router doesn't pull in OCR-heavy deps.
    """
    from app.utils.pdf_ocr import ocr_pdf_to_rows as _impl
    return _impl(content)


def _ocrmypdf_then_extract_tables(content: bytes) -> list[list[list[str]]]:
    """Thin delegating wrapper around app.utils.pdf_ocr.ocrmypdf_then_extract_tables.

    See `_ocr_pdf_to_rows` above — same reasoning, same "keep name/signature,
    delegate the body" approach.
    """
    from app.utils.pdf_ocr import ocrmypdf_then_extract_tables as _impl
    return _impl(content)


def _extract_html_tables(content: bytes, filename: str = "doc.html") -> list[list[list[str]]]:
    """Single source of truth for HTML→tables extraction.

    Used by BOTH /items/import-preview AND /items/import-mapped so that table
    indices ("Таблица 1", "Таблица 2"...) refer to the same tables in both
    endpoints. Order: markitdown → parse_markdown_tables, fallback BeautifulSoup.
    """
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
        # Classify once, only if pdfplumber didn't already find tables — the
        # classification subprocess isn't free, no point paying for it when
        # pdfplumber's native table extraction already succeeded.
        _ocr_pages: list[int] | None = None
        if not raw_tables:
            try:
                from app.utils.pdf_classify import inspect_pdf as _inspect_pdf_classify
                _insp = _inspect_pdf_classify(content)
                if _insp.ok:
                    _ocr_pages = _insp.ocr_pages or None
                    logger.info(
                        "_legacy_extract_tables: pdf_classify pdf_type=%s ocr_pages=%s (classifier path)",
                        _insp.pdf_type, _insp.ocr_pages,
                    )
                else:
                    logger.info("_legacy_extract_tables: pdf classification failed (%s), OCR-ing whole document", _insp.error)
            except Exception as e:
                logger.warning("_legacy_extract_tables: pdf classification unavailable, OCR-ing whole document: %s", e)
        if not raw_tables:
            # Try ocrmypdf — adds OCR layer, then pdfplumber extracts tables natively
            ocr_tables = _ocrmypdf_then_extract_tables(content)
            if ocr_tables:
                raw_tables.extend(ocr_tables)
        if not raw_tables:
            # Last resort: raw OCR via image_to_data, with preprocessing + PSM
            # auto-selection, restricted to pdf-inspector's flagged pages when
            # classification succeeded (whole document otherwise).
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
    """Detect УПД (Универсальный передаточный документ) numeric label row.

    УПД standard column layout (Постановление Правительства РФ № 1137):
      1   — № п/п
      1а  — код товара/работ/услуг (артикул)
      1б  — Наименование товара (описание выполненных работ, оказанных услуг)
      1в  — код вида товара
      2   — единица измерения, код
      2а  — единица измерения, условное обозначение
      3   — Количество (объем)
      4   — Цена (тариф) за единицу
      5   — Стоимость без налога
      6   — В т.ч. сумма акциза
      7   — Налоговая ставка
      8   — Сумма налога
      9   — Стоимость С НАЛОГОМ - всего
      10  — Страна происхождения - код
      10а — Страна происхождения - название
      11  — Регистрационный номер декларации

    Returns column mapping dict or None if row doesn't match УПД pattern.
    Match rule: ≥4 of {'1а','1б','2','2а','3','4','5','9'} present.

    2026-10-02 (owner-verified against 3 real УПД: nf110.xls/cb97.pdf/
    u1643.pdf, см. backend/tests/test_upd_import_real_layout.py): в файлах
    владельца колонка «Наименование товара» печатается ПОД сублейблом '1а',
    не '1б' (textbook-раскладка 1137 называет их наоборот, но этот модуль
    доверяет реальным файлам, не учебнику) — '1б' остаётся fallback-ом для
    документов, где всё же встречается обратный порядок.
    """
    LABELS = {'1а', '1б', '2', '2а', '3', '4', '5', '9'}
    found = {}
    for i, h in enumerate(row):
        h_s = h.strip().lower().replace(' ', '')
        if h_s in LABELS or h_s in {'1', '6', '7', '8', '10', '10а', '11', '12', '12а', '13'}:
            found[h_s] = i
    if len(LABELS & set(found.keys())) < 4:
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
    # Стоимость БЕЗ налога (col 5) — храним отдельно от total_price (который
    # предпочитает «с налогом», col 9): нужна для определения режима «НДС
    # сверху» и как fallback, когда колонки 9 в документе нет вовсе.
    if '5' in found:
        col['total_wo_tax'] = found['5']
    # Prefer total WITH tax (col 9), fallback to without-tax (col 5)
    if '9' in found:
        col['total_price'] = found['9']
    elif '5' in found:
        col['total_price'] = found['5']
    if '2а' in found:
        col['unit'] = found['2а']
    if '2' in found:
        col['unit_code'] = found['2']  # цифровой код ОКЕИ (напр. 796 → шт)
        col.setdefault('unit', found['2'])
    # Задача «НДС сверху» (02.10.2026): колонка 7 — налоговая ставка. col '4'
    # (цена за единицу) в УПД — БЕЗ налога, col '9' (стоимость с налогом) —
    # с налогом: ровно «цена без НДС + сумма с НДС» — единственный признак,
    # что эта таблица распознана как УПД (см. is_upd в _legacy_detect_best_table).
    if '7' in found:
        col['vat_rate'] = found['7']
    if '8' in found:
        col['vat_amount'] = found['8']
    return col if 'item_name' in col else None


# ---------------------------------------------------------------------------
# УПД — единый детектор раскладки (Правило №6, задача import-upd-detector,
# 2026-10-02): раньше колонки УПД разбирались дважды — здесь позиционно по
# кодам (_detect_upd_layout выше) и ОТДЕЛЬНО во фронте
# (useItemsImport.ts::autoDetectMapping, тот же набор меток). Теперь это
# единственное место, которое и находит строку кодов, и разбирает позиции —
# find_upd_code_row/parse_upd_table/build_upd_sheet_extra ниже используются
# и xlsx-путём (_smart_import_xlsx_direct), и /items/import-preview
# (PDF/DOCX/HTML/Excel), и markitdown-фоллбэком smart-импорта
# (_legacy_detect_best_table выше). Фронт применяет готовый auto_mapping,
# второй копии детектора там больше нет.
UPD_OKEI_UNITS = {
    '796': 'шт', '006': 'м', '868': 'компл.', '112': 'л', '166': 'кг',
    '055': 'м2', '113': 'м3', '245': 'усл.ед.', '876': 'усл.ед.',
    '704': 'компл.', '163': 'г', '350': 'упак.', '778': 'компл.',
}


def _okei_to_unit(code: str | None) -> str | None:
    """Код ОКЕИ (напр. '796') → условное обозначение ('шт'). None, если код
    не распознан или пуст — не выдумываем единицу, которой нет в справочнике."""
    if not code:
        return None
    c = str(code).strip()
    if not c or c in ('--', '-', '—'):
        return None
    c_norm = c.lstrip('0') or '0'
    return UPD_OKEI_UNITS.get(c) or UPD_OKEI_UNITS.get(c_norm) or UPD_OKEI_UNITS.get(c_norm.zfill(3))


# Эвристика «повреждённая при извлечении ячейка»: цифра впритык к кириллической
# букве внутри одного значения (напр. «1 640,0б0е» вместо «1 640,00» — соседняя
# колонка «без акциза» наехала на цифры при разборе PDF-таблицы). to_decimal
# на таком значении может случайно дать правильное число (регэксп-фоллбэк
# берёт только первую цифру после разделителя), но полагаться на удачу нельзя —
# помечаем предупреждением и пересчитываем по кол-во×цена×(1+ставка).
_UPD_CORRUPTED_CELL_RE = re.compile(r'[0-9][а-яА-Я]|[а-яА-Я][0-9]')


def find_upd_code_row(rows: list[list], search_limit: int = 30) -> tuple[int, dict] | None:
    """Ищет строку кодов УПД (А|1|1а|1б|2|2а|3|4|5|6|7|8|9|10|10а|11) в первых
    `search_limit` строках таблицы — шире, чем _legacy_detect_best_table
    (8 строк): в xls строка кодов отделена от текстовой шапки двумя строками,
    в pdf обычно одной, плюс в начале документа могут быть служебные строки
    (ссылка на постановление, «Исправление №» и т.п.). Возвращает
    (индекс строки, маппинг колонок) с НАИБОЛЬШИМ числом распознанных меток,
    либо None, если ни одна строка не похожа на строку кодов."""
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
    """Разбирает позиции УПД из строк ПОСЛЕ строки кодов до строки
    «Всего к оплате» (включительно — останавливается на ней).

    unit_price = колонка 4 (БЕЗ налога); total_price = колонка 9 (С НАЛОГОМ),
    либо колонка 5 (без налога), если колонки 9 в документе нет вовсе —
    задача «НДС сверху» (02.10.2026): при col 9 отдельно от col 5 позиция
    помечена как УПД-схема (contract_vat_on_top) выше по стеку (вызывающий
    роутер читает 'total_wo_tax' in col). Единица — col 2а, либо перевод кода
    ОКЕИ (col 2) через _okei_to_unit.

    Возвращает {"items": [...], "warnings": [...], "columns_found": [...]}.
    """
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
        # Ячейка УПД из PDF приходит с переносами строк — в позицию одной строкой.
        name = " ".join((_cell(row, 'item_name') or "").split())
        if not name:
            continue
        quantity = _to_dec(_cell(row, 'quantity'))
        unit_price = _to_dec(_cell(row, 'unit_price'))
        vat_rate_raw = _cell(row, 'vat_rate')
        unit_val = _cell(row, 'unit')
        if not unit_val:
            unit_val = _okei_to_unit(_cell(row, 'unit_code'))
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
    """Если `all_rows` распознаются как таблица УПД — вернуть overrides для
    sheet-словаря /items/import-preview (header_row_offset/auto_mapping/
    is_upd/preview/warnings), иначе None. auto_mapping — то же сопоставление
    полей → индекс колонки, которое раньше заново вычислял фронт
    (useItemsImport.ts::autoDetectMapping) — единственный источник теперь
    здесь, фронт только применяет."""
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
    """Fallback column detection on raw tables.

    Возвращает (best_table, best_col, best_header_row, is_upd) — is_upd=True,
    когда таблица распознана по числовым меткам УПД (_detect_upd_layout) —
    единственный признак «цена колонки 4 без налога, колонка 9 с налогом»,
    задача «НДС сверху» (02.10.2026) читает его, чтобы проставить
    contract_vat_on_top/vat_on_top автоматически (см. покупатели ниже)."""
    def _detect_columns_legacy(header_row: list[str]) -> dict:
        col: dict = {}
        for i, h in enumerate(header_row):
            h_s = h.strip().lower()
            # УПД precise headers (priority)
            if 'наименование товара' in h_s or 'описание выполненных' in h_s or 'описание оказанных' in h_s:
                col.setdefault("item_name", i)
            elif any(x in h_s for x in (
                "наименован", "назван", "name", "товар", "предмет", "описан",
                "услуг", "работ",
                # import-pdf-debug C2: билетный формат
                "маршрут", "направлен", "рейс", "билет",
            )):
                col.setdefault("item_name", i)
            elif any(x in h_s for x in ("тип", "type", "вид")):
                col.setdefault("item_type", i)
            elif any(x in h_s for x in ("количество (объем)", "кол-во", "количеств", "qty", "quantity")) or h_s.startswith("кол"):
                col.setdefault("quantity", i)
            elif "ед. изм" in h_s or "единиц" in h_s or "ед.изм" in h_s or h_s == "ед." or h_s == "unit":
                col.setdefault("unit", i)
            elif any(x in h_s for x in (
                "цена", "тариф", "price",
                # import-pdf-debug C2: стоимость единицы / тариф билета
                "стоимость", "сумма билет", "цена билет",
            )):
                col.setdefault("unit_price", i)
            # VAT columns (import-vat-cols C2)
            elif any(x in h_s for x in ("ставка ндс", "налоговая ставка", "% ндс", "ндс %", "vat rate")):
                col.setdefault("vat_rate", i)
            elif any(x in h_s for x in ("сумма ндс", "vat amount")):
                col.setdefault("vat_amount", i)
            # Total: prefer "с налогом", else "без налога"/"стоимость"/"сумма"
            elif "с налогом" in h_s and "всего" in h_s:
                col["total_price"] = i  # always overwrite — highest priority
            elif any(x in h_s for x in ("к оплате", "сумма с налогом", "итого с ндс")):
                col["total_price"] = i  # import-pdf-debug C2: билетные итоги
            elif "total_price" not in col and any(x in h_s for x in ("сумма", "итог", "total", "amount", "всего", "стоимость")):
                col["total_price"] = i
        return col

    best_table: list[list[str]] = []
    best_col: dict = {}
    best_header_row = 0
    # First pass: try УПД numeric-label detection (positional mapping)
    for table in raw_tables:
        for r_idx, row in enumerate(table[:8]):
            upd_col = _detect_upd_layout(row)
            if upd_col and len(upd_col) > len(best_col):
                best_col = upd_col
                best_table = table
                best_header_row = r_idx
    if best_col:
        return best_table, best_col, best_header_row, True
    # Second pass: keyword-based detection (legacy)
    for table in raw_tables:
        for r_idx, row in enumerate(table[:6]):
            col = _detect_columns_legacy(row)
            if "item_name" in col and len(col) > len(best_col):
                best_col = col
                best_table = table
                best_header_row = r_idx
    return best_table, best_col, best_header_row, False



# ---------------------------------------------------------------------------
# Image import helpers (Phase 26-PP)
# ---------------------------------------------------------------------------

def _try_decode_qr(image_bytes: bytes) -> str | None:
    """Попытаться декодировать QR-код из изображения.

    Сначала pyzbar, потом cv2.QRCodeDetector. Возвращает строку QR или None.
    Все импорты в try/except — если библиотек нет, вернуть None без ошибок.

    Владелец (уточнение 2026-09-29): «TIF/HEIC — тоже попробовать распознать».
    TIFF Pillow открывает нативно без доп. библиотек. HEIC/HEIF — только если
    зарегистрирован pillow-heif opener (пакет уже в requirements.txt,
    используется покадрово в purchase_items_import_smart.py/wish_export.py —
    здесь регистрируем тем же вызовом ЦЕНТРАЛЬНО, чтобы каждый вызывающий
    _try_decode_qr (в т.ч. новый receipt_pdf_qr.py) получил HEIC бесплатно,
    вместо копирования register_heif_opener() в каждое место (ПРАВИЛО №6).
    Best-effort — если пакета вдруг нет, PIL.Image.open ниже просто не
    распознает HEIC и упадёт в except, как и раньше.
    """
    try:
        import pillow_heif as _pillow_heif
        _pillow_heif.register_heif_opener()
    except Exception:
        pass

    # pyzbar
    try:
        from pyzbar.pyzbar import decode as _pyzbar_decode
        from PIL import Image as _PILImage
        import io as _io
        img = _PILImage.open(_io.BytesIO(image_bytes))
        decoded = _pyzbar_decode(img)
        for d in decoded:
            data = d.data
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            if data:
                return data
    except Exception:
        pass

    # cv2 fallback
    try:
        import cv2 as _cv2
        import numpy as _np
        arr = _np.frombuffer(image_bytes, dtype=_np.uint8)
        img_cv = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
        if img_cv is not None:
            detector = _cv2.QRCodeDetector()
            data, _, _ = detector.detectAndDecode(img_cv)
            if data:
                return data
    except Exception:
        pass

    return None


def _smart_import_image_ocr(content: bytes, filename: str) -> dict:
    """Stage 1 OCR для изображений: tesseract → regex-парсинг строк чека.

    Возвращает preview-словарь (без сохранения в БД).
    Бросает HTTPException если OCR пустой или ничего не распознано.
    """
    import re

    # Открыть изображение через Pillow
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Не удалось открыть изображение: {e}")

    # OCR
    try:
        import pytesseract
        ocr_text = pytesseract.image_to_string(img, lang="rus+eng")
    except Exception as e:
        raise HTTPException(
            400,
            f"Ошибка OCR (tesseract установлен?): {e}. "
            "Попробуйте QR-чек ФНС или загрузите Excel/PDF."
        )

    if not ocr_text or not ocr_text.strip():
        raise HTTPException(
            400,
            "На изображении не распознан текст. "
            "Попробуйте QR-чек ФНС или загрузите Excel/PDF с позициями."
        )

    # Эвристика: каждая строка — потенциальная позиция
    # Паттерны: «Название  N шт  X руб», «Название  X руб», «1  Название  N  X  Y»
    items = []
    lines = [ln.strip() for ln in ocr_text.splitlines() if ln.strip()]

    # Паттерн: число-разделитель-название-число(кол-во)-число(цена)-число(сумма)
    # Или проще: ищем строки с хотя бы одним числом-рублём
    PRICE_RE = re.compile(
        r"(?P<name>.+?)\s+"
        r"(?:(?P<qty>\d+(?:[.,]\d+)?)\s*(?:шт|кг|л|м|уп|уп\.|ед|ед\.)\s*)?"
        r"(?:x|х|×)?\s*"
        r"(?P<price>\d[\d\s]*(?:[.,]\d{1,2})?)\s*(?:руб|₽|р\.?)?",
        re.IGNORECASE | re.UNICODE,
    )
    SKIP_WORDS = re.compile(
        r"^(итого|total|сумма|кассир|кассa|чек|receipt|дата|дата:|inn|инн|"
        r"тел|телефон|спасибо|магазин|адрес|режим|номер|фн:|фд:|фпд:|"
        r"кку|ккт|ооо|ип |ооо )",
        re.IGNORECASE,
    )

    for line in lines:
        if SKIP_WORDS.match(line):
            continue
        m = PRICE_RE.search(line)
        if not m:
            continue
        name = m.group("name").strip(" -–•·")
        # Слишком короткое название — пропустить
        if len(name) < 3:
            continue
        qty_raw = m.group("qty")
        price_raw = m.group("price")
        try:
            price_clean = price_raw.replace(" ", "").replace(",", ".")
            price_val = float(price_clean)
        except Exception:
            price_val = None
        try:
            qty_val = float((qty_raw or "1").replace(",", "."))
        except Exception:
            qty_val = 1.0

        items.append({
            "item_name": name[:500],
            "item_type": "товар",
            "quantity": qty_val,
            "unit": "шт",
            "unit_price": price_val,
            "total_price": round(price_val * qty_val, 2) if price_val else None,
        })

    if not items:
        raise HTTPException(
            400,
            "На изображении текст распознан, но позиции товаров не обнаружены. "
            "Качество OCR для чеков невысокое — рекомендуем использовать QR-код ФНС "
            "(приложение «Проверка чека ФНС России») или загрузить Excel/PDF."
        )

    return {
        "preview": items,
        "total_rows": len(items),
        "file_type": "image_ocr",
        "columns_found": ["item_name", "quantity", "unit_price", "total_price"],
        "warning": (
            "Распознавание через OCR имеет ограниченную точность. "
            "Рекомендуется проверить позиции перед сохранением. "
            "Для лучшего результата используйте QR-код ФНС на чеке."
        ),
    }


def _looks_mojibake(wb) -> bool:
    """Эвристика: если в первом листе ≥50% строковых ячеек состоят целиком из latin-1 акцент-символов
    (U+00C0..U+00FF) либо содержат U+FFFD — считаем что cp1251 декодировалась как latin-1."""
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
            # доля символов в диапазоне latin-1 supplement (0xC0..0xFF) — типичный признак cp1251→latin1
            latin_supp = sum(1 for ch in s if 0x00C0 <= ord(ch) <= 0x00FF)
            if latin_supp >= max(2, len(s) // 2):
                bad += 1
    return total > 0 and bad / total >= 0.5


def _read_excel_rows(content: bytes, fname: str) -> list[list[list]]:
    """Универсальное чтение Excel: возвращает list[sheets], каждый sheet = list[rows], row = list[cells].
    Поддерживает .xlsx (openpyxl) и .xls BIFF8 (xlrd с авто-cp1251-override при mojibake)."""
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
    """Direct XLSX/XLS parser without markitdown — устойчив к опечаткам в заголовке,
    разделам-подзаголовкам в середине, multi-line cells, merged headers.
    Поддерживает .xls BIFF8 с авто-cp1251-override при mojibake.

    Returns (preview_rows, columns_found, warnings).
    Каждый dict в preview_rows: row (номер строки файла), item_name, item_type,
    quantity, unit, unit_price, total_price.
    warnings — Дефект 2 (владелец, 2026-09-14): sum_mismatch, если в строке
    заданы кол-во, цена И сумма, а произведение с суммой не сходится (см.
    app/services/qty_price_check.py — тот же допуск/текст, что у ФЭО-импорта).
    """
    import re as _re

    # Header keywords (substring match, case-insensitive, tolerant к опечаткам через 'in')
    # Шаг 5 (владелец, 2026-08-07): 'unit_price' проверяется РАНЬШЕ 'unit' —
    # заголовок «Цена за единицу» содержит подстроку «единиц», которая раньше
    # матчилась ключом 'unit' первой (dict сохраняет порядок вставки, matching
    # идёт по порядку ключей) — колонка цены никогда не находилась, unit_price/
    # total_price молча оставались None. Тот же баг, что и в _detect_columns_legacy
    # (см. комментарий там) — независимая копия той же логики (проект уже
    # предупреждал о дублировании normalize/tokenize, см. план шаг 4).
    HEADER_PATTERNS = {
        'item_name': ['наимен', 'товар', 'позици', 'описан', 'материал', 'предмет'],
        'item_type': ['тип', 'вид'],
        'quantity': ['колич', 'кол-во', 'кол.', 'кол ', 'кол.во', 'qty'],  # ловит "Количечество"
        'unit_price': ['цена за ед', 'цена ед', 'цена/ед', 'цена', 'unit price', 'стоимость ед'],
        'unit': ['ед.из', 'ед. изм', 'едизм', 'единиц', 'unit'],
        'total_price': ['сумма', 'итого', 'стоимость', 'total'],
    }

    try:
        sheets = _read_excel_rows(content, fname)
    except Exception:
        return [], [], []
    all_rows: list[list] = [r for sh in sheets for r in sh]

    # УПД (Правило №6, задача import-upd-detector 2026-10-02): пробуем ЕДИНЫЙ
    # детектор раскладки ДО общего keyword-парсера ниже. Для УПД общий
    # заголовочный эвристик (HEADER_PATTERNS) ошибочно матчит «Код товара/
    # работ, услуг» на item_name (подстрока «товар» матчит раньше настоящей
    # колонки «Наименование товара») — живой пример: nf110.xls владельца,
    # где «наименование» получалось равным «НФ-00000340» (код товара), а
    # количество/сумма оставались пустыми.
    _upd = find_upd_code_row(all_rows)
    if _upd:
        _code_row_idx, _col = _upd
        _res = parse_upd_table(all_rows, _code_row_idx, _col)
        if _res["items"]:
            return _res["items"], _res["columns_found"], _res["warnings"]

    def _classify_header(row: list) -> dict:
        """Return dict {col_idx -> field_key} для cells матчащихся к HEADER_PATTERNS."""
        mapping: dict[int, str] = {}
        for idx, cell in enumerate(row):
            if cell is None:
                continue
            text = str(cell).lower().strip()
            if not text:
                continue
            for field, patterns in HEADER_PATTERNS.items():
                if any(p in text for p in patterns):
                    if field not in mapping.values():  # первый match выигрывает
                        mapping[idx] = field
                    break
        return mapping

    # Выбираем строку с наибольшим числом распознанных колонок (≥3 полей лучше 2)
    # — защита от ложного срабатывания на строки-итоги типа «Товар по листу…»
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
    header_idx = best_idx
    col_map = best_map

    if header_idx == -1:
        return [], [], []

    # Inverse map: field -> col_idx
    field_to_idx = {v: k for k, v in col_map.items()}
    columns_found = list(field_to_idx.keys())

    _to_dec = to_decimal

    def _get_cell(row: list, field: str):
        idx = field_to_idx.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        return v if v not in (None, '') else None

    TYPE_MAP = {
        'товар': 'товар', 'товары': 'товар',
        'услуга': 'услуга', 'услуги': 'услуга',
        'работа': 'работа', 'работы': 'работа',
    }

    preview: list[dict] = []
    warnings: list[dict] = []
    # Номер строки файла = header_idx (0-based) + 2 (сам заголовок — строка
    # header_idx+1, данные начинаются со следующей) + порядковый номер в цикле.
    for i, row in enumerate(all_rows[header_idx + 1:]):
        row_num = header_idx + 2 + i
        name_val = _get_cell(row, 'item_name')
        if name_val is None:
            continue
        name = str(name_val).strip().replace('\n', ' ').replace('\r', ' ')
        name = _re.sub(r'\s+', ' ', name)
        if not name:
            continue
        # Пропускаем разделы-подзаголовки: нет ни qty, ни цены, ни суммы
        qty = _to_dec(_get_cell(row, 'quantity'))
        unit_price = _to_dec(_get_cell(row, 'unit_price'))
        total_price = _to_dec(_get_cell(row, 'total_price'))
        if qty is None and unit_price is None and total_price is None:
            continue
        # Дефект 2 (владелец, 2026-09-14): кол-во × цена ≠ сумма из файла —
        # предупреждение по ИСХОДНЫМ (не дозаполненным ниже) значениям.
        _mismatch = check_qty_price_sum(row_num, name, qty, unit_price, total_price)
        if _mismatch:
            warnings.append(_mismatch)
        # Вычисляем недостающее
        if unit_price is None and total_price is not None and qty:
            try:
                unit_price = total_price / qty
            except Exception:
                pass
        if total_price is None and unit_price is not None and qty:
            total_price = line_total(qty, unit_price)
        unit_val = _get_cell(row, 'unit')
        unit_raw = str(unit_val).strip() if unit_val else None  # без дефолта — для бэкфилла Product.unit
        unit = unit_raw or 'шт'
        type_val = _get_cell(row, 'item_type')
        item_type = TYPE_MAP.get(str(type_val).lower().strip() if type_val else '', 'товар')
        preview.append({
            'row': row_num,
            'item_name': name,
            'item_type': item_type,
            'quantity': float(qty) if qty else None,
            'unit': unit,
            'unit_raw': unit_raw,
            'unit_price': float(unit_price) if unit_price else None,
            'total_price': float(total_price) if total_price else None,
        })
    return preview, columns_found, warnings
