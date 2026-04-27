"""Purchase items-import router — extracted from purchases.py (Phase 16-03).

Handles:
  GET  /api/purchases/items/import/template       — download blank xlsx template
  POST /api/purchases/{pid}/items/import          — bulk import from Excel (legacy)
  POST /api/purchases/items/import-preview        — parse file, return headers/samples for mapping
  POST /api/purchases/{pid}/items/import-mapped   — import using user-specified column mapping
  POST /api/purchases/{pid}/items/import-smart    — smart AI-assisted import (markitdown + fallback)
  GET  /api/purchases/import/feo-format/template  — download FEO-format template
  POST /api/purchases/import/feo-format           — import purchases from FEO 57-column format

OCR helpers (_ocr_pdf_to_rows, _legacy_extract_tables, _legacy_detect_best_table) and
the product-catalog upsert helper (_upsert_product_to_catalog) live in this module.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
from typing import Optional
from decimal import Decimal
from datetime import datetime, date

from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.product import Product
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.auth.jwt import get_current_user, require_role, get_single_org_id, MANAGER_ROLES
from app.auth.permissions import require_tab
from app.models.user import User

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None
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

router = APIRouter(prefix="/api/purchases", tags=["purchase-items-import"])


# ---------------------------------------------------------------------------
# OCR / legacy table-extraction helpers
# ---------------------------------------------------------------------------

def _ocr_pdf_to_rows(content: bytes) -> tuple[list, str | None]:
    """Convert scanned PDF to rows via OCR with layout awareness.
    Uses pytesseract image_to_data (TSV) — gives bounding boxes per word.
    Group words into rows by y-coordinate, then split into columns by
    x-gaps within each row. Returns (rows, error_message).
    """
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError:
        return [], "OCR-библиотеки не установлены (pdf2image, pytesseract). Обратитесь к администратору."
    try:
        # 400 DPI gives noticeably better recognition on receipts/invoices than 300
        images = convert_from_bytes(content, dpi=400)
    except Exception as e:
        return [], f"Не удалось преобразовать PDF в изображения для OCR (poppler установлен?): {e}"
    if not images:
        return [], "PDF не содержит страниц для распознавания."

    all_rows: list[list[str]] = []
    for img in images:
        try:
            # PSM 6 = "Assume a single uniform block of text" — best for tables/lists
            data = pytesseract.image_to_data(
                img, lang='rus+eng', config='--psm 6',
                output_type=pytesseract.Output.DICT,
            )
        except Exception as e:
            return [], f"Ошибка OCR-распознавания (tesseract установлен?): {e}"

        # Group words by (block_num, par_num, line_num) → one OCR line each
        n = len(data.get('text', []))
        line_buckets: dict[tuple, list] = {}
        for i in range(n):
            word = (data['text'][i] or '').strip()
            if not word:
                continue
            try:
                conf = int(data['conf'][i])
            except (ValueError, TypeError):
                conf = -1
            if conf < 0:
                continue
            key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
            line_buckets.setdefault(key, []).append({
                'text': word,
                'left': int(data['left'][i]),
                'right': int(data['left'][i]) + int(data['width'][i]),
                'top': int(data['top'][i]),
            })

        # Sort lines top-to-bottom by mean y-coord of their words
        sorted_lines = sorted(
            line_buckets.values(),
            key=lambda ws: sum(w['top'] for w in ws) / len(ws),
        )

        for words in sorted_lines:
            words.sort(key=lambda w: w['left'])
            # Split into cells: gap > 40px between adjacent words = new column
            GAP_PX = 40
            cells: list[str] = []
            current = words[0]['text']
            prev_right = words[0]['right']
            for w in words[1:]:
                if w['left'] - prev_right > GAP_PX:
                    cells.append(current)
                    current = w['text']
                else:
                    current += ' ' + w['text']
                prev_right = w['right']
            cells.append(current)
            cells = [c.strip() for c in cells if c.strip()]
            if cells:
                all_rows.append(cells)

    if not all_rows:
        return [], "OCR не нашёл текст на страницах. Возможно, качество скана слишком низкое."
    return all_rows, None


def _ocrmypdf_then_extract_tables(content: bytes) -> list[list[list[str]]]:
    """Run ocrmypdf on scanned PDF (adds invisible OCR text layer),
    then extract tables via pdfplumber from the OCR'd PDF.
    Returns list of tables (each = list of rows). Empty list on failure.
    """
    try:
        import ocrmypdf
        import pdfplumber as _pp
    except ImportError as e:
        logger.warning("ocrmypdf or pdfplumber not installed: %s", e)
        return []
    import tempfile, os
    in_path = out_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as fin:
            fin.write(content)
            in_path = fin.name
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as fout:
            out_path = fout.name
        # force_ocr=True even if pdf has some text — scans often have garbage text layer
        # skip_text=False ensures all pages get OCR'd
        try:
            ocrmypdf.ocr(
                in_path, out_path,
                language='rus+eng',
                force_ocr=True,
                deskew=True,
                clean=True,
                progress_bar=False,
                output_type='pdf',
            )
        except Exception as e:
            logger.warning("ocrmypdf failed: %s", e)
            return []
        # Now extract tables from the OCR'd PDF
        tables_out: list[list[list[str]]] = []
        try:
            with _pp.open(out_path) as pdf:
                for page in pdf.pages:
                    for tbl in (page.extract_tables() or []):
                        if tbl:
                            cleaned = [[str(c).strip() if c else "" for c in row] for row in tbl]
                            if any(any(c for c in row) for row in cleaned):
                                tables_out.append(cleaned)
                    # If no tables detected, fall back to text lines as virtual table
                    if not tables_out:
                        text = page.extract_text() or ""
                        if text.strip():
                            import re
                            rows = []
                            for line in text.split('\n'):
                                line = line.strip()
                                if not line:
                                    continue
                                cells = re.split(r'  {2,}|\t', line)
                                cells = [c.strip() for c in cells if c.strip()]
                                if cells:
                                    rows.append(cells)
                            if rows:
                                tables_out.append(rows)
        except Exception as e:
            logger.warning("pdfplumber on OCR'd PDF failed: %s", e)
            return []
        return tables_out
    finally:
        for p in (in_path, out_path):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


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
        if not raw_tables:
            # Try ocrmypdf — adds OCR layer, then pdfplumber extracts tables natively
            ocr_tables = _ocrmypdf_then_extract_tables(content)
            if ocr_tables:
                raw_tables.extend(ocr_tables)
        if not raw_tables:
            # Last resort: raw OCR via image_to_data
            ocr_rows, _ = _ocr_pdf_to_rows(content)
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


def _legacy_detect_best_table(raw_tables: list[list[list[str]]]) -> tuple:
    """Fallback column detection on raw tables."""
    def _detect_columns_legacy(header_row: list[str]) -> dict:
        col: dict = {}
        for i, h in enumerate(header_row):
            h_s = h.strip().lower()
            if any(x in h_s for x in ("наименован", "назван", "name", "товар", "предмет", "описан", "услуг")):
                col.setdefault("item_name", i)
            elif any(x in h_s for x in ("тип", "type", "вид")):
                col.setdefault("item_type", i)
            elif any(x in h_s for x in ("кол", "количеств", "qty", "quantity")):
                col.setdefault("quantity", i)
            elif any(x in h_s for x in ("ед.", "единиц", "unit", "изм")):
                col.setdefault("unit", i)
            elif any(x in h_s for x in ("цена ед", "цена за", "стоимость ед", "price")):
                col.setdefault("unit_price", i)
            elif any(x in h_s for x in ("сумма", "итог", "total", "amount", "всего", "стоимость")):
                col.setdefault("total_price", i)
        return col
    best_table: list[list[str]] = []
    best_col: dict = {}
    best_header_row = 0
    for table in raw_tables:
        for r_idx, row in enumerate(table[:6]):
            col = _detect_columns_legacy(row)
            if "item_name" in col and len(col) > len(best_col):
                best_col = col
                best_table = table
                best_header_row = r_idx
    return best_table, best_col, best_header_row


# ---------------------------------------------------------------------------
# Product-catalog upsert helper
# ---------------------------------------------------------------------------

async def _upsert_product_to_catalog(db, item_name: str, item_type: str, unit_price, description: str = "") -> int:
    """Find or create a product in the global catalog. Returns product.id."""
    norm = item_name.strip().lower()
    existing = (await db.execute(
        select(Product).where(func.lower(Product.name) == norm)
    )).scalar_one_or_none()
    if existing:
        return existing.id
    p = Product(
        name=item_name.strip(),
        description=description or "",
        product_type=item_type or "товар",
        price=Decimal(str(unit_price)) if unit_price else Decimal("0"),
        is_active=True,
    )
    db.add(p)
    await db.flush()
    return p.id


# ---------------------------------------------------------------------------
# Purchase items import from Excel
# ---------------------------------------------------------------------------

@router.get("/items/import/template")
async def items_import_template(_=Depends(require_tab('purchases'))):
    """Download xlsx template for bulk purchase items import."""
    if not Workbook:
        raise HTTPException(500, "openpyxl не установлен")

    wb = Workbook()
    ws = wb.active
    ws.title = "Позиции"

    headers = ["Наименование", "Описание / ТЗ", "Тип (товар/услуга/работа)", "Количество", "Ед. изм.", "Цена за единицу"]
    required = {"Наименование"}

    header_fill = PatternFill("solid", fgColor="1E40AF")
    req_fill = PatternFill("solid", fgColor="1D4ED8")
    header_font = Font(bold=True, color="FFFFFF")

    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = header_font
        cell.fill = req_fill if h in required else header_fill
        cell.alignment = Alignment(horizontal="center")

    example = ["Ноутбук Lenovo ThinkPad", "Технические характеристики...", "товар", "5", "шт", "85000"]
    for ci, val in enumerate(example, 1):
        ws.cell(row=2, column=ci, value=val)

    col_widths = [45, 50, 25, 15, 15, 20]
    for ci, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = w

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=items_template.xlsx"},
    )


@router.post("/{pid}/items/import")
async def import_items_excel(
    pid: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk import items into a purchase from Excel."""
    fname = (file.filename or '').lower()
    if not fname.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx / .xls")

    purchase = await db.get(Purchase, pid)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    content = await file.read()
    try:
        if fname.endswith('.xls'):
            try:
                import xlrd as _xlrd_mod
            except ImportError:
                raise HTTPException(500, "xlrd не установлен")
            wb_xls = _xlrd_mod.open_workbook(file_contents=content)
            ws_xls = wb_xls.sheet_by_index(0)
            all_rows = [tuple(ws_xls.row_values(i)) for i in range(ws_xls.nrows)]
            header_row = all_rows[0] if all_rows else None
            data_iter = all_rows[1:] if len(all_rows) > 1 else []
        else:
            if not load_workbook:
                raise HTTPException(500, "openpyxl не установлен")
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            all_rows_gen = list(ws.iter_rows(values_only=True))
            header_row = all_rows_gen[0] if all_rows_gen else None
            data_iter = all_rows_gen[1:] if len(all_rows_gen) > 1 else []
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")
    if not header_row:
        raise HTTPException(400, "Файл пустой")

    def _norm(v) -> str:
        return str(v).strip().lower() if v else ''

    # Fuzzy column mapping
    col: dict[str, int] = {}
    for i, h in enumerate(header_row):
        h_str = _norm(h)
        if any(x in h_str for x in ('наименован', 'назван', 'name', 'товар', 'предмет')):
            col.setdefault('item_name', i)
        elif any(x in h_str for x in ('описан', 'description', 'тз', 'техническ', 'specification', 'характерист')):
            col.setdefault('description', i)
        elif any(x in h_str for x in ('тип', 'type', 'вид')):
            col.setdefault('item_type', i)
        elif any(x in h_str for x in ('кол', 'количеств', 'qty', 'quantity')):
            col.setdefault('quantity', i)
        elif any(x in h_str for x in ('ед.', 'единиц', 'unit', 'изм')):
            col.setdefault('unit', i)
        elif any(x in h_str for x in ('цена', 'price', 'стоимость', 'за единиц')):
            col.setdefault('unit_price', i)

    if 'item_name' not in col:
        raise HTTPException(400, "Не найдена колонка с наименованием.")

    def _cell(row, field):
        idx = col.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        if v is None:
            return None
        s = str(v).strip()
        if not s or s.lower() in ('none', 'null', '-', '—'):
            return None
        return s

    def _to_dec(v):
        if v is None:
            return None
        try:
            return Decimal(str(v).replace(',', '.').replace(' ', ''))
        except Exception:
            return None

    # Load products for auto-matching by name
    org_id = get_single_org_id(current_user)
    prod_q = select(Product)
    if org_id:
        prod_q = prod_q.where((Product.org_id == org_id) | (Product.org_id.is_(None)))
    prod_result = await db.execute(prod_q)
    products = prod_result.scalars().all()
    # Build name lookup (lowercase → product)
    product_by_name: dict[str, Product] = {}
    for p in products:
        if p.name:
            product_by_name[p.name.lower().strip()] = p

    TYPE_MAP = {
        'товар': 'товар', 'товары': 'товар', 'product': 'товар', 'goods': 'товар',
        'услуга': 'услуга', 'услуги': 'услуга', 'service': 'услуга',
        'работа': 'работа', 'работы': 'работа', 'work': 'работа',
    }

    added = 0
    matched_catalog = 0
    new_in_catalog = 0
    errors_list = []

    for row in data_iter:
        item_name = _cell(row, 'item_name')
        if not item_name:
            continue

        description = _cell(row, 'description')
        item_type_raw = (_cell(row, 'item_type') or 'товар').lower().strip()
        item_type = TYPE_MAP.get(item_type_raw, 'товар')
        quantity = _to_dec(_cell(row, 'quantity')) or Decimal('1')
        unit = _cell(row, 'unit') or 'шт'
        unit_price = _to_dec(_cell(row, 'unit_price'))
        total_price = (quantity * unit_price) if unit_price else None

        # Auto-match or create in catalog
        matched_product = product_by_name.get(item_name.lower().strip())
        if matched_product:
            product_id = matched_product.id
            matched_catalog += 1
            if not unit_price and matched_product.price:
                unit_price = matched_product.price
                total_price = quantity * unit_price
        else:
            product_id = await _upsert_product_to_catalog(db, item_name, item_type, unit_price, description or "")
            product_by_name[item_name.lower().strip()] = type('_P', (), {'id': product_id, 'name': item_name, 'price': unit_price})()
            new_in_catalog += 1

        item = PurchaseItem(
            purchase_id=pid,
            product_id=product_id,
            item_name=item_name,
            item_type=item_type,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
            total_price=total_price,
        )
        db.add(item)
        added += 1

    await db.commit()
    return {"added": added, "matched_catalog": matched_catalog, "new_in_catalog": new_in_catalog, "errors": errors_list}


# ---------------------------------------------------------------------------
# Excel import with column mapping (preview + mapped import)
# ---------------------------------------------------------------------------

@router.post("/items/import-preview")
async def import_items_preview(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Read Excel/PDF/DOCX file and return sheets, headers, and sample rows for column mapping."""
    fname = (file.filename or '').lower()
    if not fname.endswith(('.xlsx', '.xls', '.pdf', '.docx', '.doc', '.html', '.htm')):
        raise HTTPException(400, "Поддерживаются файлы .xlsx, .xls, .pdf, .docx, .html")

    content = await file.read()

    _NAME_HINTS = ('наименован', 'назван', 'товар', 'предмет', 'name', 'title', 'услуг', 'работ')
    _ALL_HINTS = _NAME_HINTS + ('цена', 'описан', 'кол', 'тип', 'price', 'стоимост', 'ед.', 'единиц', 'катег', 'сумм', 'количеств', 'ед. изм')

    def _detect_hdr(rows):
        best_score, best_idx = 0, 0
        for ri, row in enumerate(rows):
            norm = [str(h).strip().lower() if h is not None else "" for h in row]
            score = sum(1 for h in norm if h and any(x in h for x in _ALL_HINTS))
            if score > best_score:
                best_score = score; best_idx = ri
        return best_idx

    try:
        # ── PDF ──
        if fname.endswith('.pdf'):
            try:
                import pdfplumber
            except ImportError:
                raise HTTPException(500, "pdfplumber не установлен")
            pdf = pdfplumber.open(BytesIO(content))
            all_rows = []
            text_lines = []
            for page in pdf.pages:
                # Try tables
                for t in (page.extract_tables() or []):
                    if t:
                        all_rows.extend([[str(c).strip() if c else "" for c in row] for row in t])
                # Also collect text lines as fallback
                for line in (page.extract_text() or "").split('\n'):
                    line = line.strip()
                    if line:
                        text_lines.append(line)
            pdf.close()
            if not all_rows and text_lines:
                # Split text lines by tabs/multiple spaces to detect columns
                import re
                for line in text_lines:
                    parts = re.split(r'\t|  +', line)
                    all_rows.append([p.strip() for p in parts if p.strip()])
            if not all_rows:
                # Try ocrmypdf — adds OCR text layer, then pdfplumber reads tables natively
                ocr_tables = _ocrmypdf_then_extract_tables(content)
                if ocr_tables:
                    for tbl in ocr_tables:
                        all_rows.extend(tbl)
            if not all_rows:
                # Last resort: raw pixel OCR
                all_rows, ocr_error = _ocr_pdf_to_rows(content)
                if not all_rows:
                    detail = ocr_error or "OCR не смог распознать таблицу."
                    raise HTTPException(
                        400,
                        f"Этот PDF — скан (изображение). {detail} "
                        "Попробуйте сохранить данные в Excel (.xlsx) или Word (.docx)."
                    )
            hdr_idx = _detect_hdr(all_rows)
            headers = [str(h).strip() if h else f"Столбец {j+1}" for j, h in enumerate(all_rows[hdr_idx])]
            data = all_rows[hdr_idx + 1:]
            sample = [[str(c) if c else "" for c in r] for r in data[:5]]
            return {"sheets": [{"name": "PDF", "headers": headers, "sample": sample, "total_rows": len(data), "header_row_offset": hdr_idx}]}

        # ── DOCX ──
        if fname.endswith(('.docx', '.doc')):
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
            sample = [[str(c) if c else "" for c in r] for r in data[:5]]
            return {"sheets": [{"name": "Document", "headers": headers, "sample": sample, "total_rows": len(data), "header_row_offset": hdr_idx}]}

        # ── HTML ──
        if fname.endswith(('.html', '.htm')):
            try:
                from app.utils.document_to_markdown import file_to_markdown, parse_markdown_tables
                md_text = file_to_markdown(content, file.filename or fname)
                raw_tables = parse_markdown_tables(md_text)
            except Exception as e:
                logger.warning("markitdown HTML parse failed: %s", e)
                raw_tables = []
            if not raw_tables:
                # Fallback: BeautifulSoup
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(content, 'html.parser')
                    raw_tables = []
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
            if not raw_tables:
                raise HTTPException(400, "В HTML-файле не найдено таблиц с данными.")
            # Return ALL tables as separate "sheets" so user can pick which one to import
            sheets_html = []
            for ti, tbl_rows in enumerate(raw_tables, start=1):
                if len(tbl_rows) < 2:
                    continue  # skip tables with no data
                hdr_idx = _detect_hdr(tbl_rows)
                headers = [str(h).strip() if h else f"Столбец {j+1}" for j, h in enumerate(tbl_rows[hdr_idx])]
                data = tbl_rows[hdr_idx + 1:]
                sample = [[str(c) if c else "" for c in r] for r in data[:5]]
                sheets_html.append({
                    "name": f"Таблица {ti}",
                    "headers": headers,
                    "sample": sample,
                    "total_rows": len(data),
                    "header_row_offset": hdr_idx,
                })
            if not sheets_html:
                raise HTTPException(400, "В HTML-файле не найдено таблиц с достаточным количеством строк.")
            return {"sheets": sheets_html}

        # ── Excel ──
        if fname.endswith('.xls'):
            try:
                import xlrd as _xlrd_mod
            except ImportError:
                raise HTTPException(500, "xlrd не установлен")
            wb_xls = _xlrd_mod.open_workbook(file_contents=content)
            sheets = []
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
                sample = [[str(c).strip() if c is not None else "" for c in row] for row in hdr_rows[1:min(6, len(hdr_rows))]]
                sheets.append({"name": sheet_name, "headers": headers, "sample": sample,
                               "total_rows": ws_xls.nrows - hdr_idx - 1, "header_row_offset": hdr_idx})
        else:
            if not load_workbook:
                raise HTTPException(500, "openpyxl не установлен")
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
            sheets = []
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
                sample = [[str(c).strip() if c is not None else "" for c in row] for row in hdr_rows[1:min(6, len(hdr_rows))]]
                sheets.append({"name": sheet_name, "headers": headers, "sample": sample,
                               "total_rows": len(all_rows) - hdr_idx - 1, "header_row_offset": hdr_idx})
            wb.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл ({file.filename}): {e}")

    if not sheets:
        raise HTTPException(400, "Файл не содержит листов с данными")

    return {"sheets": sheets}


@router.post("/{pid}/items/import-mapped")
async def import_items_mapped(
    pid: int,
    file: UploadFile = File(...),
    sheet_name: str = Query(""),
    col_item_name: int = Query(-1, description="Индекс столбца Наименование (0-based)"),
    col_description: int = Query(-1, description="Индекс столбца Описание"),
    col_quantity: int = Query(-1, description="Индекс столбца Количество"),
    col_unit_price: int = Query(-1, description="Индекс столбца Цена"),
    col_total_price: int = Query(-1, description="Индекс столбца Сумма"),
    col_vat: int = Query(-1, description="Индекс столбца НДС"),
    col_unit: int = Query(-1, description="Индекс столбца Ед. изм."),
    header_row_offset: int = Query(0, description="Сколько строк пропустить до заголовка (авто-определено при preview)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import items using user-specified column mapping."""
    if col_item_name < 0:
        raise HTTPException(400, "Не указан столбец Наименование")

    purchase = await db.get(Purchase, pid)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    fname = (file.filename or '').lower()
    content = await file.read()

    try:
        if fname.endswith(('.docx', '.doc')):
            # Word document — extract table rows
            try:
                from docx import Document as _DDoc
            except ImportError:
                raise HTTPException(500, "python-docx не установлен")
            doc = _DDoc(BytesIO(content))
            all_rows_doc = []
            for table in doc.tables:
                for row in table.rows:
                    all_rows_doc.append(tuple(cell.text.strip() for cell in row.cells))
            if not all_rows_doc:
                for para in doc.paragraphs:
                    text = para.text.strip()
                    if text:
                        all_rows_doc.append((text,))
            skip = header_row_offset + 1
            data_iter = all_rows_doc[skip:] if len(all_rows_doc) > skip else []
        elif fname.endswith('.pdf'):
            # PDF — extract table rows
            try:
                import pdfplumber
            except ImportError:
                raise HTTPException(500, "pdfplumber не установлен")
            pdf = pdfplumber.open(BytesIO(content))
            all_rows_pdf = []
            for page in pdf.pages:
                for t in (page.extract_tables() or []):
                    if t:
                        all_rows_pdf.extend([tuple(str(c).strip() if c else "" for c in row) for row in t])
            pdf.close()
            skip = header_row_offset + 1
            data_iter = all_rows_pdf[skip:] if len(all_rows_pdf) > skip else []
        elif fname.endswith(('.html', '.htm')):
            # HTML — extract table rows via BeautifulSoup
            try:
                from bs4 import BeautifulSoup
            except ImportError:
                raise HTTPException(500, "beautifulsoup4 не установлен")
            soup = BeautifulSoup(content, 'html.parser')
            # sheet_name in HTML preview = "Таблица 1", "Таблица 2", ... (fallback: largest)
            tables = soup.find_all('table')
            if not tables:
                raise HTTPException(400, "В HTML не найдено таблиц")
            chosen = None
            if sheet_name and sheet_name.lower().startswith('таблица'):
                try:
                    idx = int(sheet_name.split()[-1]) - 1
                    if 0 <= idx < len(tables):
                        chosen = tables[idx]
                except (ValueError, IndexError):
                    pass
            if chosen is None:
                # Fallback: pick largest table
                chosen = max(tables, key=lambda t: len(t.find_all('tr')))
            all_rows_html = []
            for tr in chosen.find_all('tr'):
                cells = tuple(td.get_text(strip=True) for td in tr.find_all(['td', 'th']))
                if any(c for c in cells):
                    all_rows_html.append(cells)
            skip = header_row_offset + 1
            data_iter = all_rows_html[skip:] if len(all_rows_html) > skip else []
        elif fname.endswith('.xls'):
            try:
                import xlrd as _xlrd_mod
            except ImportError:
                raise HTTPException(500, "xlrd не установлен")
            wb_xls = _xlrd_mod.open_workbook(file_contents=content)
            ws_xls = wb_xls.sheet_by_name(sheet_name) if sheet_name else wb_xls.sheet_by_index(0)
            all_rows = [tuple(ws_xls.row_values(i)) for i in range(ws_xls.nrows)]
            skip = header_row_offset + 1
            data_iter = all_rows[skip:] if len(all_rows) > skip else []
        else:
            if not load_workbook:
                raise HTTPException(500, "openpyxl не установлен")
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
            ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
            all_rows_gen = list(ws.iter_rows(values_only=True))
            skip = header_row_offset + 1
            data_iter = all_rows_gen[skip:] if len(all_rows_gen) > skip else []
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл ({file.filename}): {e}")

    def _cell(row, idx):
        if idx < 0 or idx >= len(row):
            return None
        v = row[idx]
        if v is None:
            return None
        s = str(v).strip()
        if not s or s.lower() in ('none', 'null', '-', '—', '0'):
            return None
        return s

    def _to_dec(v):
        if v is None:
            return None
        try:
            s = str(v).replace(',', '.').replace(' ', '').replace('\xa0', '')
            # Strip non-numeric suffix (e.g. "руб.", "шт.", "р.")
            import re
            m = re.match(r'^([0-9]+\.?[0-9]*)', s)
            if not m:
                return None
            return Decimal(m.group(1))
        except Exception:
            return None

    # Load products for auto-matching
    org_id = get_single_org_id(current_user)
    prod_q = select(Product)
    if org_id:
        prod_q = prod_q.where((Product.org_id == org_id) | (Product.org_id.is_(None)))
    prod_result = await db.execute(prod_q)
    products = prod_result.scalars().all()
    product_by_name: dict[str, Product] = {}
    for p in products:
        if p.name:
            product_by_name[p.name.lower().strip()] = p

    added = 0
    matched_catalog = 0
    new_in_catalog = 0
    errors_list = []
    skipped_empty = 0      # row[col_item_name] is None/empty
    skipped_junk = 0       # _is_junk_row matched
    total_data_rows = 0    # счётчик прошедших data_iter

    # Keywords that indicate non-product rows (totals, footers, signatures)
    _SKIP_KEYWORDS = {
        'итого', 'всего', 'итог', 'total', 'подитог', 'subtotal',
        'поставщик', 'покупатель', 'заказчик', 'исполнитель',
        'генеральный директор', 'директор', 'бухгалтер', 'подпись',
        'м.п.', 'м.п', 'печать', 'ооо', 'оао', 'зао', 'ип ',
        'инн', 'кпп', 'огрн', 'р/с', 'к/с', 'бик',
        'адрес', 'телефон', 'email', 'банк',
        'примечание', 'основание', 'договор №', 'счёт №', 'счет №',
    }

    def _is_junk_row(name_val: str) -> bool:
        """Check if this looks like a footer/total/signature row, not a product."""
        low = name_val.lower().strip()
        # Direct match with skip keywords
        for kw in _SKIP_KEYWORDS:
            if low.startswith(kw) or low == kw:
                return True
        # Row starts with "итого" variants like "Итого с НДС:", "Итого:"
        if low.startswith('итого'):
            return True
        return False

    for row_idx, row in enumerate(data_iter):
        try:
            total_data_rows += 1
            item_name = _cell(row, col_item_name)
            if not item_name:
                skipped_empty += 1
                continue

            # Skip junk rows (totals, footers, signatures)
            if _is_junk_row(item_name):
                skipped_junk += 1
                continue

            description = _cell(row, col_description) if col_description >= 0 else None
            quantity = _to_dec(_cell(row, col_quantity)) if col_quantity >= 0 else Decimal('1')
            if not quantity:
                quantity = Decimal('1')
            unit_price = _to_dec(_cell(row, col_unit_price)) if col_unit_price >= 0 else None
            total_price = _to_dec(_cell(row, col_total_price)) if col_total_price >= 0 else None
            unit = (_cell(row, col_unit) if col_unit >= 0 else None) or 'шт'

            # Calculate missing values
            if not total_price and unit_price:
                total_price = quantity * unit_price
            elif not unit_price and total_price and quantity:
                unit_price = total_price / quantity

            # VAT info → append to description
            vat_str = _cell(row, col_vat) if col_vat >= 0 else None
            if vat_str and description:
                description = f"{description} (НДС: {vat_str})"
            elif vat_str:
                description = f"НДС: {vat_str}"

            # Auto-match or create in catalog
            matched_product = product_by_name.get(item_name.lower().strip())
            if matched_product:
                product_id = matched_product.id
                matched_catalog += 1
                if not unit_price and matched_product.price:
                    unit_price = matched_product.price
                    total_price = quantity * unit_price
            else:
                product_id = await _upsert_product_to_catalog(db, item_name, 'товар', unit_price, description or "")
                product_by_name[item_name.lower().strip()] = type('_P', (), {'id': product_id, 'name': item_name, 'price': unit_price})()
                new_in_catalog += 1

            item = PurchaseItem(
                purchase_id=pid,
                product_id=product_id,
                item_name=item_name,
                item_type='товар',
                quantity=quantity,
                unit=unit,
                unit_price=unit_price,
                total_price=total_price,
            )
            db.add(item)
            added += 1
        except Exception as e:
            errors_list.append(f"Строка {row_idx + 1}: {e}")
            await db.rollback()
            continue

    try:
        await db.commit()
    except Exception as e:
        raise HTTPException(500, f"Ошибка сохранения: {e}")
    return {
        "added": added,
        "matched_catalog": matched_catalog,
        "new_in_catalog": new_in_catalog,
        "errors": errors_list,
        "debug": {
            "total_rows_after_header": len(data_iter),
            "rows_processed": total_data_rows,
            "skipped_empty_name": skipped_empty,
            "skipped_junk_row": skipped_junk,
            "first_3_rows_sample": [list(r)[:8] for r in data_iter[:3]],
        },
    }


@router.post("/{pid}/items/import-smart")
async def import_items_smart(
    pid: int,
    file: UploadFile = File(...),
    confirm: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Smart import: extract items table from PDF / DOCX / XLSX."""
    purchase = await db.get(Purchase, pid)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")
    # Employees can import to any purchase they have access to
    if current_user.role not in MANAGER_ROLES and current_user.role not in ("employee",):
        raise HTTPException(403, "Insufficient permissions")

    content = await file.read()
    filename = (file.filename or "").lower()

    allowed_ext = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".html", ".htm")
    if not any(filename.endswith(ext) for ext in allowed_ext):
        raise HTTPException(400, "Поддерживаются файлы: PDF, DOCX, XLSX/XLS, HTML")

    if filename.endswith(".pdf"):
        file_type = "pdf"
    elif filename.endswith((".xlsx", ".xls")):
        file_type = "excel"
    elif filename.endswith((".html", ".htm")):
        file_type = "html"
    else:
        file_type = "docx"

    # --- Stage 1: Convert to Markdown via markitdown ---
    from app.utils.document_to_markdown import (
        file_to_markdown, parse_markdown_tables, pick_best_table, detect_columns,
    )

    try:
        md_text = file_to_markdown(content, file.filename or filename)
    except Exception as e:
        logger.warning("markitdown conversion failed: %s", e)
        raise HTTPException(400, f"Не удалось обработать файл: {e}")

    # --- Stage 2: Extract tables from Markdown ---
    raw_tables = parse_markdown_tables(md_text)

    # Fallback: if markitdown found no tables, try legacy direct parsing
    if not raw_tables:
        raw_tables = _legacy_extract_tables(content, filename, file_type)

    if not raw_tables:
        raise HTTPException(
            400,
            "Таблицы в документе не найдены. "
            "Убедитесь что документ содержит таблицу с колонкой «Наименование»."
        )

    # --- Stage 3: Detect columns ---
    result = pick_best_table(raw_tables)
    if result is None:
        # Fallback: manual column detection on raw tables
        best_table, best_col, best_header_row = _legacy_detect_best_table(raw_tables)
    else:
        best_table, best_header_row = result
        best_col = detect_columns(best_table[best_header_row])

    if not best_table or "item_name" not in best_col:
        raise HTTPException(400, "Не удалось найти таблицу с позициями. Убедитесь что документ содержит колонку «Наименование».")

    TYPE_MAP = {
        "товар": "товар", "товары": "товар", "product": "товар",
        "услуга": "услуга", "услуги": "услуга", "service": "услуга",
        "работа": "работа", "работы": "работа",
    }

    def _to_dec(v: str):
        if not v:
            return None
        try:
            cleaned = v.replace(",", ".").replace(" ", "").replace("\xa0", "").replace("–", "").replace("—", "")
            return Decimal(cleaned)
        except Exception:
            return None

    def _parse_row(row: list[str]):
        def _get(field: str) -> str:
            idx = best_col.get(field)
            if idx is None or idx >= len(row):
                return ""
            v = row[idx].strip()
            return "" if v.lower() in ("none", "null", "-", "—", "") else v

        item_name = _get("item_name")
        if not item_name:
            return None
        item_type = TYPE_MAP.get(_get("item_type").lower(), "товар")
        quantity = _to_dec(_get("quantity"))
        unit = _get("unit") or "шт"
        unit_price = _to_dec(_get("unit_price"))
        total_price = _to_dec(_get("total_price"))
        if unit_price is None and total_price is not None and quantity:
            try:
                unit_price = total_price / quantity
            except Exception:
                pass
        if total_price is None and unit_price is not None and quantity:
            total_price = unit_price * (quantity or Decimal("1"))
        return {
            "item_name": item_name,
            "item_type": item_type,
            "quantity": float(quantity) if quantity else None,
            "unit": unit,
            "unit_price": float(unit_price) if unit_price else None,
            "total_price": float(total_price) if total_price else None,
        }

    data_rows = best_table[best_header_row + 1:]
    preview = [r for r in (_parse_row(row) for row in data_rows[:100]) if r]

    if not confirm:
        return {"preview": preview, "total_rows": len(preview), "file_type": file_type, "columns_found": list(best_col.keys())}

    # Save items to DB
    org_id = get_single_org_id(current_user)
    prod_q = select(Product)
    if org_id:
        prod_q = prod_q.where((Product.org_id == org_id) | (Product.org_id.is_(None)))
    products = (await db.execute(prod_q)).scalars().all()
    product_by_name = {(p.name or "").lower().strip(): p for p in products}

    added = matched_catalog = new_in_catalog = 0
    for row_data in preview:
        item_name = (row_data["item_name"] or "")[:500]
        qty = Decimal(str(row_data["quantity"])) if row_data["quantity"] else Decimal("1")
        unit_price = Decimal(str(row_data["unit_price"])) if row_data["unit_price"] else None
        total_price = Decimal(str(row_data["total_price"])) if row_data["total_price"] else None
        matched = product_by_name.get(item_name.lower().strip())
        if matched:
            product_id = matched.id
            matched_catalog += 1
            if not unit_price and matched.price:
                unit_price = matched.price
                total_price = qty * unit_price
        else:
            product_id = await _upsert_product_to_catalog(db, item_name, row_data["item_type"], unit_price)
            new_in_catalog += 1
        if total_price is None and unit_price:
            total_price = qty * unit_price
        db.add(PurchaseItem(
            purchase_id=pid, product_id=product_id,
            item_name=item_name, item_type=row_data["item_type"],
            quantity=qty, unit=row_data["unit"],
            unit_price=unit_price, total_price=total_price,
        ))
        added += 1
    await db.commit()
    return {"added": added, "matched_catalog": matched_catalog, "new_in_catalog": new_in_catalog}


# ---------------------------------------------------------------------------
# FEO-format import (57-column layout, headers in row 6)
# ---------------------------------------------------------------------------

FEO_HEADERS = [
    "№ п.п.", "Вид расходов", "Номер субсидии",
    "Номер строки плана закупок", "Категория расходов (ФЭО направление)",
    "Наименование товара", "Контрагент", "Количество поставлено",
    "Ед. изм.", "Стоимость единицы по смете", "Стоимость по плану всего",
    "Подтверждено", "Контрактная цена за единицу", "Стоимость контракта",
    "НМЦК всего", "НМЦК по субсидии", "КПП поставщика",
    "Номер договора", "Дата договора", "Номер ПП",
    "Описание платёжного поручения", "Дата платежа", "Сумма оплаты",
    "Всего исполнено", "Резерв 25", "Резерв 26", "Резерв 27",
    "Статус закупки", "Соответствие НДС (законодательство)", "НДС включён",
    "Соответствие требованиям НДС", "Страна происхождения", "Модель",
    "Номер категории ФЭО", "Статус исполнения", "Процент исполнения",
    "Остаток по обязательствам", "Срок исполнения", "Ссылка на торговую площадку",
    "НДС-расчёт", "Совместные", "Прямой контракт",
    "Прямой контракт (повторный)", "Малые контракты", "Конкурсные",
    "Дата последнего изменения", "Стоимость единицы по оплате", "Итого к оплате",
    "Субсидия", "Часть расходов (направление)", "Период",
    "Оплата", "Сумма НДС", "Счётчик",
    "Описание контракта", "Номер и дата платежа", "",
]


def _feo_find_header_row(rows: list) -> int:
    """Return 0-based index of the header row (first row with >=5 non-empty cells)."""
    for i, row in enumerate(rows[:10]):
        non_empty = sum(1 for c in row if c is not None and str(c).strip())
        if non_empty >= 5:
            return i
    return 0


@router.get("/import/feo-format/template")
async def download_feo_template(_=Depends(require_tab('purchases'))):
    """Скачать шаблон Excel в ФЭО-формате (57 колонок, заголовки в строке 6)."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")

    wb = Workbook()
    ws = wb.active
    ws.title = "ФЭО закупки"

    # Rows 1-5: instruction header (merged across all columns)
    ws.merge_cells("A1:BE5")
    instr_cell = ws["A1"]
    instr_cell.value = (
        "ШАБЛОН ДЛЯ ЗАГРУЗКИ ЗАКУПОК В ФЭО-ФОРМАТЕ\n"
        "Строка 6 — заголовки колонок (не изменять).\n"
        "Начиная со строки 7 — данные.\n"
        "Субсидия определяется автоматически по категории ФЭО (колонка 5).\n"
        "Обязательные колонки: 5 (ФЭО направление), 6 (Наименование товара)."
    )
    instr_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    instr_cell.font = Font(bold=True, size=11)
    ws.row_dimensions[1].height = 80

    # Row 6: headers
    ws.append(FEO_HEADERS)
    header_fill = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    for cell in ws[6]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[6].height = 35

    # Row 7: example
    ws.append([
        1, "Товары", "", "1",
        "Направление 1 - Техническое оснащение",
        "Компьютер офисный", "ООО Поставщик", 5, "шт",
        "50000", "250000", "да",
        "48000", "240000", "260000", "260000",
        "771234567890", "Д-001/2026", "15.03.2026",
        "70", "Оплата по договору Д-001/2026", "20.03.2026", "240000",
        "", "", "", "",
        "исполнено", "", "", "", "Россия", "", "",
        "оплачено", "1", "0",
        "30.06.2026", "", "", "", "", "", "", "",
        "", "", "", "", "", "", "", "2026",
        "240000", "0", "", "70 от 20.03.2026", "",
    ])
    ws.row_dimensions[7].height = 20

    ws.freeze_panes = "A7"

    # Column widths
    col_widths = [6, 12, 10, 12, 40, 35, 30, 10, 8, 14, 14, 12,
                  14, 14, 14, 14, 14, 18, 14, 10, 30, 14, 14, 14,
                  10, 10, 10, 14, 25, 14, 25, 18, 14, 14, 16, 12,
                  14, 14, 30, 12, 12, 16, 18, 14, 12, 16, 14, 14,
                  16, 20, 10, 14, 12, 20, 30, 20, 8]
    for i, w in enumerate(col_widths, 1):
        if i <= ws.max_column:
            ws.column_dimensions[ws.cell(6, i).column_letter].width = w

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=feo_import_template.xlsx"},
    )


@router.post("/import/feo-format")
async def import_feo_format(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('purchases')),
):
    """Импорт закупок из ФЭО-формата (57 колонок, заголовки в строке 6).
    Субсидия определяется автоматически через feo_category.subsidy_id.
    """
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx и .xls")

    content = await file.read()
    wb = load_workbook(BytesIO(content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(400, "Файл пустой")

    header_idx = _feo_find_header_row(rows)
    header_row = rows[header_idx]

    # Build column index by position keyword matching
    def _norm(v) -> str:
        return str(v).strip().lower() if v is not None else ""

    col: dict[str, int] = {}
    for i, h in enumerate(header_row):
        hn = _norm(h)
        if not hn:
            continue
        if "наименован" in hn or "товар" in hn or "услуг" in hn:
            col.setdefault("item_name", i)
        elif "вид расход" in hn or "вид" == hn:
            col.setdefault("item_type", i)
        elif "категори" in hn and ("фэо" in hn or "расход" in hn or "направлен" in hn):
            col.setdefault("feo_name", i)
        elif "контрагент" in hn:
            col.setdefault("contractor_name", i)
        elif "количеств" in hn or "кол-во" in hn:
            col.setdefault("quantity", i)
        elif "ед. изм" in hn or "единиц" in hn:
            col.setdefault("unit", i)
        elif "стоимость единицы по смете" in hn or ("стоимость" in hn and "единиц" in hn and "смет" in hn):
            col.setdefault("planned_unit_price", i)
        elif "стоимость по плану" in hn or ("стоимость" in hn and "план" in hn):
            col.setdefault("planned_total_price", i)
        elif "подтвержд" in hn:
            col.setdefault("confirmed", i)
        elif "стоимость контракта" in hn or ("стоимость" in hn and "контракт" in hn):
            col.setdefault("contract_price", i)
        elif "нмцк" in hn and "субсидии" not in hn:
            col.setdefault("nmck", i)
        elif "кпп" in hn:
            col.setdefault("kpp", i)
        elif "номер договора" in hn or ("номер" in hn and "договор" in hn):
            col.setdefault("contract_number", i)
        elif "дата договора" in hn or ("дата" in hn and "договор" in hn):
            col.setdefault("contract_date", i)
        elif "номер пп" in hn or ("номер" in hn and "платёжн" in hn) or ("номер" in hn and "поручен" in hn):
            col.setdefault("payment_doc_number", i)
        elif "дата платежа" in hn or ("дата" in hn and "платеж" in hn):
            col.setdefault("payment_doc_date", i)
        elif "сумма оплаты" in hn or ("сумма" in hn and "оплат" in hn):
            col.setdefault("payment_amount", i)
        elif "срок исполнения" in hn or ("срок" in hn and "исполнен" in hn):
            col.setdefault("execution_term", i)
        elif "сумма ндс" in hn:
            col.setdefault("vat_amount", i)

    # Fallback: use positional mapping (column indices 0-based from FEO_HEADERS order)
    # Col 5(idx=4)=feo, 6(5)=item_name, 7(6)=contractor, 8(7)=qty, 9(8)=unit,
    # 10(9)=unit_price, 11(10)=planned_total, 12(11)=confirmed, 14(13)=contract_price,
    # 15(14)=nmck, 17(16)=kpp, 18(17)=contract_num, 19(18)=contract_date,
    # 20(19)=pp_num, 22(21)=pp_date, 23(22)=payment_amount, 38(37)=execution_term, 53(52)=vat
    POSITIONAL = {
        "feo_name": 4, "item_name": 5, "item_type": 1,
        "contractor_name": 6, "quantity": 7, "unit": 8,
        "planned_unit_price": 9, "planned_total_price": 10, "confirmed": 11,
        "contract_price": 13, "nmck": 14, "kpp": 16,
        "contract_number": 17, "contract_date": 18,
        "payment_doc_number": 19, "payment_doc_date": 21, "payment_amount": 22,
        "execution_term": 37, "vat_amount": 52,
    }
    if "item_name" not in col and len(header_row) >= 57:
        # Headers didn't match keywords — use positional
        col = {k: v for k, v in POSITIONAL.items()}

    if "item_name" not in col and "feo_name" not in col:
        raise HTTPException(400, "Не удалось найти колонки наименования или ФЭО. Проверьте формат файла.")

    # Load lookup tables
    feo_rows = (await db.execute(select(FeoCategory))).scalars().all()
    feo_by_name: dict[str, FeoCategory] = {}
    for f in feo_rows:
        feo_by_name[f.name.lower().strip()] = f

    cont_rows = (await db.execute(select(Contractor))).scalars().all()
    cont_by_name: dict[str, int] = {c.name.lower().strip(): c.id for c in cont_rows}
    cont_by_kpp: dict[str, int] = {c.kpp.strip(): c.id for c in cont_rows if c.kpp}

    org_id = get_single_org_id(current_user)

    def _cell(row, field) -> Optional[str]:
        idx = col.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        if v is None:
            return None
        s = str(v).strip()
        return s if s and s.lower() not in ("none", "null", "-", "—", "") else None

    def _to_dec(v) -> Optional[Decimal]:
        if v is None:
            return None
        try:
            return Decimal(str(v).replace(",", ".").replace(" ", "").replace("\xa0", ""))
        except Exception:
            return None

    def _to_date(v) -> Optional[date]:
        if v is None:
            return None
        if isinstance(v, (date, datetime)):
            return v.date() if isinstance(v, datetime) else v
        s = str(v).strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
        return None

    created = 0
    skipped = 0
    errors_list = []

    data_start = header_idx + 1
    for row_num, row in enumerate(rows[data_start:], start=data_start + 1):
        item_name = _cell(row, "item_name")
        if not item_name:
            skipped += 1
            continue

        # FEO lookup → subsidy
        feo_name_raw = _cell(row, "feo_name")
        feo_obj = None
        if feo_name_raw:
            feo_obj = feo_by_name.get(feo_name_raw.lower().strip())
            if not feo_obj:
                # Partial match
                for k, v in feo_by_name.items():
                    if feo_name_raw.lower() in k or k in feo_name_raw.lower():
                        feo_obj = v
                        break

        if feo_obj is None:
            errors_list.append({"row": row_num, "name": item_name, "message": f"ФЭО категория не найдена: {feo_name_raw!r}"})
            skipped += 1
            continue

        feo_category_id = feo_obj.id
        subsidy_id = feo_obj.subsidy_id

        # Contractor lookup
        cont_name = _cell(row, "contractor_name")
        kpp_raw = _cell(row, "kpp")
        contractor_id = None
        if cont_name:
            contractor_id = cont_by_name.get(cont_name.lower().strip())
            if contractor_id is None and kpp_raw:
                contractor_id = cont_by_kpp.get(kpp_raw.strip())
            if contractor_id is None:
                # Create new contractor
                new_cont = Contractor(name=cont_name, kpp=kpp_raw, org_id=org_id)
                db.add(new_cont)
                await db.flush()
                contractor_id = new_cont.id
                cont_by_name[cont_name.lower().strip()] = contractor_id
                if kpp_raw:
                    cont_by_kpp[kpp_raw.strip()] = contractor_id

        # Numeric fields
        planned_qty = _to_dec(_cell(row, "quantity"))
        planned_unit = _to_dec(_cell(row, "planned_unit_price"))
        planned_total = _to_dec(_cell(row, "planned_total_price"))
        contract_price = _to_dec(_cell(row, "contract_price"))
        nmck = _to_dec(_cell(row, "nmck"))
        payment_amount = _to_dec(_cell(row, "payment_amount"))
        vat_amount = _to_dec(_cell(row, "vat_amount"))

        # Dates
        def _raw_date(field):
            idx = col.get(field)
            if idx is None or idx >= len(row):
                return None
            return _to_date(row[idx])

        contract_date = _raw_date("contract_date")
        payment_doc_date = _raw_date("payment_doc_date")
        execution_term = _raw_date("execution_term")

        # Status inference
        contract_number = _cell(row, "contract_number")
        payment_doc_number = _cell(row, "payment_doc_number")
        if payment_amount and payment_amount > 0:
            status = "paid"
        elif contract_number:
            status = "contracted"
        else:
            status = "confirmed"

        # Confirmed flag
        conf_raw = (_cell(row, "confirmed") or "").lower()
        confirmed = conf_raw in ("да", "yes", "1", "true", "+")

        # Item type
        item_type_raw = (_cell(row, "item_type") or "").lower()
        item_type = "услуга" if "услуг" in item_type_raw else "товар"

        # VAT
        vat_applicable = bool(vat_amount and vat_amount > 0)

        p = Purchase(
            item_name=item_name,
            item_type=item_type,
            feo_category_id=feo_category_id,
            subsidy_id=subsidy_id,
            contractor_id=contractor_id,
            planned_quantity=planned_qty,
            unit=_cell(row, "unit"),
            planned_unit_price=planned_unit,
            planned_total_price=planned_total,
            confirmed=confirmed,
            contract_price=contract_price,
            nmck=nmck,
            total_nmck=nmck,
            contract_number=contract_number,
            contract_date=contract_date,
            payment_doc_number=payment_doc_number,
            payment_doc_date=payment_doc_date,
            payment_amount=payment_amount,
            execution_term=execution_term,
            vat_applicable=vat_applicable,
            status=status,
        )
        db.add(p)
        created += 1

    await db.commit()
    return {"created": created, "skipped": skipped, "errors": errors_list}
