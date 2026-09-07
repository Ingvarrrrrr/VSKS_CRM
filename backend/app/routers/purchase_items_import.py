"""Purchase items-import router — extracted from purchases.py (Phase 16-03).

Разрезание (Правило №5, сессия 2026-09-08): этот файл теперь содержит только
ядро — диагностику, legacy-импорт из Excel и предпросмотр для маппинга колонок.
Остальные эндпоинты вынесены рядом на том же префиксе "/api/purchases":
  - purchase_items_import_mapped.py — /items/import-mapped-nopid, /{pid}/items/import-mapped
  - purchase_items_import_smart.py  — /items/import-smart-nopid, /{pid}/items/import-smart,
                                       /items/import-pdf-debug
  - purchase_items_import_feo.py    — /import/feo-format/template, /import/feo-format
Общая парсинг-логика (OCR/таблицы) — в app/services/items_import_parsing.py;
общие DB-хелперы каталога — в app/services/items_import_catalog.py.

Этот модуль (ядро) содержит:
  GET  /api/purchases/items/import-debug          — диагностика OCR/парсинг-библиотек
  GET  /api/purchases/items/import/template       — download blank xlsx template
  POST /api/purchases/{pid}/items/import          — bulk import from Excel (legacy)
  POST /api/purchases/items/import-preview        — parse file, return headers/samples for mapping

_upsert_product_to_catalog переехал в app/services/items_import_catalog.py, но
импортируется здесь и ре-экспортируется без изменений — app/routers/products.py
делает `from app.routers.purchase_items_import import _upsert_product_to_catalog`.
"""
import logging
from urllib.parse import quote as _url_quote
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
from decimal import Decimal
from datetime import datetime

from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.product import Product
from app.auth.jwt import get_current_user, get_single_org_id
from app.auth.permissions import require_tab
from app.models.user import User
from app.services.product_matcher import score as _fuzzy_score, SCORE_AUTO as _SCORE_AUTO
from app.services.feo_plan import assert_tz_not_over_plan
from app.services.product_unit import backfill_product_unit
from app.services.items_import_parsing import (
    _extract_html_tables,
    _read_excel_rows,
    _ocrmypdf_then_extract_tables,
)
# Re-export: app/routers/products.py делает
# `from app.routers.purchase_items_import import _upsert_product_to_catalog`.
from app.services.items_import_catalog import _upsert_product_to_catalog

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None
    load_workbook = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/purchases", tags=["purchase-items-import"])

@router.get("/items/import-debug")
async def import_debug(current_user: User = Depends(get_current_user)):
    """Diagnostic: report which OCR/parsing libraries are loaded on the server.

    Use to debug 'PDF не распознаётся' issues. Hit GET /api/purchases/items/import-debug
    after autodeploy completes to verify tesseract/ocrmypdf binaries are installed.
    """
    out: dict = {}
    try:
        import pdfplumber  # noqa: F401
        out["pdfplumber"] = "ok"
    except Exception as e:
        out["pdfplumber"] = f"FAIL: {e}"
    try:
        import pytesseract
        out["pytesseract_python"] = "ok"
        try:
            v = pytesseract.get_tesseract_version()
            out["tesseract_binary"] = f"ok (v{v})"
            langs = pytesseract.get_languages()
            out["tesseract_langs"] = ",".join(sorted(langs))
            out["has_rus"] = "rus" in langs
        except Exception as e:
            out["tesseract_binary"] = f"FAIL: {e}"
    except Exception as e:
        out["pytesseract_python"] = f"FAIL: {e}"
    try:
        from pdf2image import convert_from_bytes  # noqa: F401
        out["pdf2image"] = "ok"
    except Exception as e:
        out["pdf2image"] = f"FAIL: {e}"
    try:
        import ocrmypdf  # noqa: F401
        out["ocrmypdf"] = "ok"
    except Exception as e:
        out["ocrmypdf"] = f"FAIL: {e}"
    try:
        from markitdown import MarkItDown  # noqa: F401
        out["markitdown"] = "ok"
    except Exception as e:
        out["markitdown"] = f"FAIL: {e}"
    try:
        from bs4 import BeautifulSoup  # noqa: F401
        out["beautifulsoup4"] = "ok"
    except Exception as e:
        out["beautifulsoup4"] = f"FAIL: {e}"
    try:
        from openpyxl import load_workbook  # noqa: F401
        out["openpyxl"] = "ok"
    except Exception as e:
        out["openpyxl"] = f"FAIL: {e}"
    # Check ghostscript (needed by ocrmypdf)
    import shutil
    out["ghostscript_bin"] = "ok" if shutil.which("gs") else "MISSING"
    out["pdftoppm_bin"] = "ok" if shutil.which("pdftoppm") else "MISSING"
    out["unpaper_bin"] = "ok" if shutil.which("unpaper") else "MISSING"
    try:
        import pdf_inspector
        out["pdf_inspector"] = f"ok (v{getattr(pdf_inspector, '__version__', '?')})"
    except Exception as e:
        out["pdf_inspector"] = f"FAIL: {e}"
    try:
        import cv2
        out["cv2"] = f"ok (v{cv2.__version__})"
    except Exception as e:
        out["cv2"] = f"FAIL: {e}"
    try:
        from app.utils.pdf_classify import inspect_pdf
        # Minimal single-page PDF with a couple of words, generated via reportlab
        # (already a dependency) rather than hand-built — just to exercise the
        # subprocess plumbing, not to assert anything about classification quality.
        from reportlab.pdfgen import canvas as _rl_canvas
        _buf = BytesIO()
        _c = _rl_canvas.Canvas(_buf)
        _c.drawString(72, 700, "VSKS import-debug test PDF")
        _c.save()
        _tiny_pdf = _buf.getvalue()
        _insp = inspect_pdf(_tiny_pdf, timeout=15)
        if _insp.ok:
            out["pdf_inspector_subprocess"] = "ok"
            # Real values from the library, not documentation guesses — for a
            # 1-page reportlab text PDF we'd *expect* pdf_type=="text",
            # ocr_pages==[], page_count==1, but show whatever actually comes back.
            out["pdf_inspector_result"] = {
                "pdf_type": _insp.pdf_type,
                "confidence": _insp.confidence,
                "page_count": _insp.page_count,
                "has_encoding_issues": _insp.has_encoding_issues,
                "ocr_pages": _insp.ocr_pages,
            }
        else:
            out["pdf_inspector_subprocess"] = f"FAIL: {_insp.error}"
    except Exception as e:
        out["pdf_inspector_subprocess"] = f"FAIL: {e}"
    return out

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
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_url_quote('Шаблон_импорта_позиций_закупки.xlsx', safe='-_.~')}"},
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
        sheets = _read_excel_rows(content, fname)
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")
    if not sheets or not sheets[0]:
        raise HTTPException(400, "Файл пустой")
    all_rows = sheets[0]  # первый лист
    header_row = all_rows[0] if all_rows else None
    data_iter = all_rows[1:] if len(all_rows) > 1 else []
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
        # Шаг 5 (владелец, 2026-08-07): проверка цены ПЕРЕД проверкой ед.изм. — заголовок
        # шаблона «Цена за единицу» (см. items_import_template выше) содержит подстроку
        # «единицу», которая раньше матчилась веткой ед.изм. ('единиц' in h_str) первой
        # (elif сверху вниз) — колонка цены никогда не находилась, unit_price/total_price
        # молча оставались NULL. Обнаружено при проверке шага 5 «ТЗ не выше плана»: гейт
        # не мог сработать, т.к. цена не читалась из файла вообще.
        elif any(x in h_str for x in ('цена', 'price', 'стоимость', 'за единиц')):
            col.setdefault('unit_price', i)
        elif any(x in h_str for x in ('ед.', 'единиц', 'unit', 'изм')):
            col.setdefault('unit', i)

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

    for row_idx, row in enumerate(data_iter, start=2):  # +1 заголовок, +1 — 1-based для пользователя
        item_name = _cell(row, 'item_name')
        if not item_name:
            continue

        description = _cell(row, 'description')
        item_type_raw = (_cell(row, 'item_type') or 'товар').lower().strip()
        item_type = TYPE_MAP.get(item_type_raw, 'товар')
        quantity = _to_dec(_cell(row, 'quantity')) or Decimal('1')
        unit_raw = _cell(row, 'unit')  # без дефолта — для бэкфилла Product.unit
        unit = unit_raw or 'шт'
        unit_price = _to_dec(_cell(row, 'unit_price'))
        total_price = (quantity * unit_price) if unit_price else None

        # Шаг 5 «цена ТЗ не выше плановой» (владелец, 2026-08-07): позиция импорта
        # наследует ФЭО-категорию закупки (feo_planned_item_id импорт не проставляет —
        # это делается отдельно, автоподбором/вручную после импорта). Ошибки
        # аггрегируем по строкам — импорт не должен падать на первой же проблемной
        # позиции, проблемные строки просто не добавляются, остальные — добавляются.
        try:
            await assert_tz_not_over_plan(
                db,
                feo_planned_item_id=None,
                feo_category_id=purchase.feo_category_id,
                quantity=quantity,
                unit_price=unit_price,
                total_price=total_price,
                item_name=item_name,
            )
        except HTTPException as _tz_exc:
            errors_list.append(f"Строка {row_idx}: {_tz_exc.detail}")
            continue

        # Auto-match or create in catalog
        # 1) exact match (fast path)
        matched_product = product_by_name.get(item_name.lower().strip())
        if not matched_product:
            # 2) fuzzy fallback — find best candidate above SCORE_AUTO threshold
            best_score = 0.0
            best_candidate = None
            for _key, _p in product_by_name.items():
                _s = _fuzzy_score(item_name, _p.name if hasattr(_p, 'name') else _key)
                if _s > best_score:
                    best_score = _s
                    best_candidate = _p
            if best_score >= _SCORE_AUTO and best_candidate is not None:
                matched_product = best_candidate
        if matched_product:
            product_id = matched_product.id
            matched_catalog += 1
            if not unit_price and matched_product.price:
                unit_price = matched_product.price
                total_price = quantity * unit_price
            if isinstance(matched_product, Product):
                await backfill_product_unit(db, matched_product, import_unit=unit_raw)
        else:
            _uname = getattr(current_user, 'full_name', None) or getattr(current_user, 'username', '') or ''
            product_id = await _upsert_product_to_catalog(
                db, item_name, item_type, unit_price, description or "",
                import_note=f"Импорт из файла «{file.filename}» (шаблон), {_uname}, {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                updated_by=_uname,
                unit=unit_raw,
            )
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

            # Heuristic: detect "garbage text layer" from scanner OCR.
            # Sharp/Xerox scanners often embed a low-quality OCR layer that pdfplumber
            # reads as text but the result is unparseable. Skip text_lines and force
            # ocrmypdf if no line has ≥10 chars with a meaningful Russian/English word.
            # This is the fallback path — kept as-is for when pdf-inspector classification
            # is unavailable, but the classifier below takes priority when it succeeds.
            import re
            def _looks_like_real_text(lines: list[str]) -> bool:
                for ln in lines:
                    # Strip non-letter chars, count alphabetic runs of length ≥4
                    words = re.findall(r"[А-Яа-яA-Za-z]{4,}", ln)
                    if len(words) >= 2 and len(ln) >= 10:
                        return True
                return False

            # Classify once per request (not once per fallback attempt — the
            # subprocess isn't free) and let it decide "garbage text layer"
            # when it's available; the home-grown heuristic above stays as the
            # fallback for when classification itself is unavailable.
            _insp = None
            _ocr_pages: list[int] | None = None
            try:
                from app.utils.pdf_classify import inspect_pdf as _inspect_pdf_classify, needs_ocr as _needs_ocr_classify
                _insp = _inspect_pdf_classify(content)
            except Exception as e:
                logger.warning("PDF preview: pdf classification unavailable, using legacy heuristic: %s", e)
                _insp = None

            if _insp is not None and _insp.ok:
                text_layer_garbage = _needs_ocr_classify(_insp)
                text_layer_usable = bool(all_rows) or not text_layer_garbage
                _ocr_pages = _insp.ocr_pages or None
                logger.info(
                    "PDF preview: decision via classifier (pdf_type=%s, has_encoding_issues=%s, "
                    "ocr_pages=%s) → text_layer_usable=%s",
                    _insp.pdf_type, _insp.has_encoding_issues, _insp.ocr_pages, text_layer_usable,
                )
            else:
                text_layer_usable = bool(all_rows) or _looks_like_real_text(text_lines)
                logger.info(
                    "PDF preview: decision via legacy heuristic (classifier %s) → text_layer_usable=%s",
                    "unavailable" if _insp is None else f"failed: {_insp.error}", text_layer_usable,
                )

            if not all_rows and text_layer_usable and text_lines:
                # Real text PDF without explicit tables — split lines by gaps
                for line in text_lines:
                    parts = re.split(r'\t|  +', line)
                    all_rows.append([p.strip() for p in parts if p.strip()])

            # If no tables AND text layer is missing or garbage → ocrmypdf
            if not all_rows or not text_layer_usable:
                if not all_rows:
                    logger.info("PDF preview: pdfplumber found no tables, trying ocrmypdf")
                else:
                    logger.info("PDF preview: text layer looks like garbage, forcing ocrmypdf")
                    all_rows = []  # discard garbage rows
                ocr_tables = _ocrmypdf_then_extract_tables(content)
                if ocr_tables:
                    for tbl in ocr_tables:
                        all_rows.extend(tbl)

            if not all_rows:
                # Last resort: raw OCR via image_to_data, with preprocessing +
                # PSM auto-selection, restricted to pdf-inspector's flagged
                # pages when classification succeeded (whole document otherwise).
                logger.info("PDF preview: ocrmypdf returned nothing, trying raw pytesseract OCR (pages=%s)", _ocr_pages)
                from app.utils.pdf_ocr import ocr_pdf_to_rows_enhanced
                all_rows, ocr_error = ocr_pdf_to_rows_enhanced(content, pages=_ocr_pages)
                if not all_rows:
                    detail = ocr_error or "OCR не смог распознать таблицу."
                    raise HTTPException(
                        400,
                        f"Этот PDF — скан (изображение). {detail} "
                        "Попробуйте сохранить данные в Excel (.xlsx) или Word (.docx) "
                        "или конвертировать PDF→HTML через Adobe Acrobat."
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
            raw_tables = _extract_html_tables(content, file.filename or fname)
            if not raw_tables:
                raise HTTPException(400, "В HTML-файле не найдено таблиц с данными.")
            # Return ALL tables as separate "sheets" so user can pick which one to import.
            # IMPORTANT: numbering MUST match _extract_html_tables — same helper is used
            # in /items/import-mapped to look up the table by name "Таблица N".
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
        raw_sheets = _read_excel_rows(content, fname)
        sheets = []
        for si, sheet_rows in enumerate(raw_sheets):
            sheet_name = f"Лист{si+1}"
            all_rows = sheet_rows
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл ({file.filename}): {e}")

    if not sheets:
        raise HTTPException(400, "Файл не содержит листов с данными")

    return {"sheets": sheets}
