"""Purchase items smart import + PDF-debug — extracted from purchase_items_import.py
(Правило №5, разрезание сессии 2026-09-08).

Handles:
  POST /api/purchases/items/import-smart-nopid  — smart XLSX preview, no purchase yet (wish/new)
  POST /api/purchases/{pid}/items/import-smart  — smart AI-assisted import (markitdown + fallback)
  POST /api/purchases/items/import-pdf-debug    — parser diagnostics for a PDF/file, no import

Same prefix as purchase_items_import.router ("/api/purchases"); all three
paths are at least 2 literal segments longer than purchases.router's
catch-all "/{pid}" (or have none), so registration order relative to it
doesn't matter (see app/routes.py comment next to purchase_items_import
imports). Registered next to purchase_items_import.router for readability.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.database import get_db
from app.models.purchase import Purchase
from app.auth.jwt import get_current_user
from app.routers.purchases import _has_purchase_write_access
from app.models.user import User
from app.services.items_import_parsing import (
    _try_decode_qr,
    _smart_import_image_ocr,
    _smart_import_xlsx_direct,
    _legacy_extract_tables,
    _legacy_detect_best_table,
)
from app.services.items_import_catalog import _save_smart_preview_to_purchase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/purchases", tags=["purchase-items-import"])

@router.post("/items/import-smart-nopid")
async def import_items_smart_nopid(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """27.4-26b: XLSX preview БЕЗ purchaseId — для wish / новой закупки.
    Возвращает все позиции через direct openpyxl парсер (не sample-only)."""
    fname = (file.filename or "").lower()
    if not fname.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Этот endpoint только для XLSX/XLS. Используйте /import-preview для других форматов.")
    content = await file.read()
    try:
        preview, columns = _smart_import_xlsx_direct(content, fname=fname)
    except Exception as e:
        logger.warning("import-smart-nopid failed: %s", e)
        ext = '.xls' if fname.endswith('.xls') else '.xlsx'
        raise HTTPException(400, f"Не удалось распознать файл ({ext}): {e}. Если файл .xls — попробуйте сохранить его как .xlsx (Excel: Файл → Сохранить как → Книга Excel) и повторите.")
    return {
        "preview": preview[:200],
        "total_rows": len(preview),
        "file_type": "excel",
        "columns_found": columns,
    }

@router.post("/{pid}/items/import-smart")
async def import_items_smart(
    pid: int,
    file: UploadFile = File(...),
    confirm: bool = Query(default=False),
    skip_catalog: bool = Query(default=False, description="Не добавлять несматченные позиции в каталог"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Smart import: extract items table from PDF / DOCX / XLSX."""
    purchase = await db.get(Purchase, pid)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")
    # Employees can import to any purchase they have access to
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав импортировать позиции в эту закупку.")

    content = await file.read()
    filename = (file.filename or "").lower()

    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")
    allowed_ext = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".html", ".htm") + IMAGE_EXTS
    if not any(filename.endswith(ext) for ext in allowed_ext):
        raise HTTPException(400, "Поддерживаются файлы: PDF, DOCX, XLSX/XLS, HTML, JPG/PNG (фото чека)")

    # ── Image pipeline ──────────────────────────────────────────────────────────
    if any(filename.endswith(ext) for ext in IMAGE_EXTS):
        # HEIC: graceful error if pillow-heif not available
        if filename.endswith((".heic", ".heif")):
            try:
                import pillow_heif  # noqa: F401
                pillow_heif.register_heif_opener()
            except ImportError:
                raise HTTPException(
                    400,
                    "Формат HEIC временно не поддерживается. "
                    "Пожалуйста, конвертируйте изображение в JPG перед загрузкой."
                )

        # Stage 0: попробовать QR-декодирование (чек ФНС)
        qr_str = _try_decode_qr(content)
        if qr_str:
            # Делегируем на proverkacheka pipeline (те же helpers что from-qr-fetch)
            from app.routers.purchase_receipts import (
                _create_receipt_with_items as _r_create_receipt,
                _parse_fns_json_receipt,
                _parse_qr_string,
            )
            import os as _os
            import httpx as _httpx
            token = _os.getenv("PROVERKACHEKA_TOKEN", "").strip()
            if not token:
                raise HTTPException(
                    503,
                    "QR-код найден, но PROVERKACHEKA_TOKEN не настроен. "
                    "Обратитесь к администратору или импортируйте Excel/PDF."
                )
            try:
                async with _httpx.AsyncClient(timeout=30.0) as _client:
                    _resp = await _client.post(
                        "https://proverkacheka.com/api/v1/check/get",
                        data={"qrraw": qr_str, "token": token},
                    )
                    _resp.raise_for_status()
                    _payload = _resp.json()
            except Exception as exc:
                raise HTTPException(502, f"Ошибка запроса к proverkacheka.com: {exc}")
            if not isinstance(_payload, dict) or _payload.get("code") != 1:
                _msg = (_payload or {}).get("data", "") if isinstance(_payload, dict) else ""
                raise HTTPException(400, f"Чек не найден в ФНС: {_msg or 'неизвестная ошибка'}")
            _body = _payload.get("data") or {}
            _receipt_obj = _body.get("json") if isinstance(_body, dict) else None
            if not isinstance(_receipt_obj, dict):
                raise HTTPException(502, "Ответ proverkacheka.com без данных чека")
            _data = _parse_fns_json_receipt(_receipt_obj)
            if not _data.get("fiscal_drive_number"):
                _qr_data = _parse_qr_string(qr_str)
                for _k, _v in _qr_data.items():
                    if _v and not _data.get(_k):
                        _data[_k] = _v
            receipt = await _r_create_receipt(
                pid, _data, "qr_scan", {"qr": qr_str, "proverkacheka": _payload}, db
            )
            return {
                "ok": True,
                "source": "qr_fns",
                "receipt_id": receipt.id,
                "message": "Чек успешно импортирован по QR-коду ФНС. Позиции добавлены в закупку.",
            }

        # Stage 1: OCR через tesseract
        return _smart_import_image_ocr(content, filename)

    if filename.endswith(".pdf"):
        file_type = "pdf"
    elif filename.endswith((".xlsx", ".xls")):
        file_type = "excel"
    elif filename.endswith((".html", ".htm")):
        file_type = "html"
    else:
        file_type = "docx"

    # 27.4-26: для XLSX обходим markitdown — direct openpyxl парсинг устойчивее
    # к опечаткам в header'е (напр. "Количечество"), разделам-подзаголовкам и multi-line cells.
    if file_type == "excel":
        try:
            xlsx_preview, xlsx_columns = _smart_import_xlsx_direct(content, fname=filename)
        except Exception as _e:
            logger.warning("Direct XLSX parser failed: %s — fallback to markitdown", _e)
            xlsx_preview, xlsx_columns = [], []
        if xlsx_preview:
            if not confirm:
                return {
                    "preview": xlsx_preview[:200],
                    "total_rows": len(xlsx_preview),
                    "file_type": file_type,
                    "columns_found": xlsx_columns,
                }
            return await _save_smart_preview_to_purchase(pid, xlsx_preview, purchase, db, current_user, skip_catalog=skip_catalog)
        # Если direct-parser не нашёл строк — fallback на markitdown (ниже)

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
        unit_raw = _get("unit") or None  # без дефолта — для бэкфилла Product.unit
        unit = unit_raw or "шт"
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
            "unit_raw": unit_raw,
            "unit_price": float(unit_price) if unit_price else None,
            "total_price": float(total_price) if total_price else None,
        }

    data_rows = best_table[best_header_row + 1:]
    preview = [r for r in (_parse_row(row) for row in data_rows[:200]) if r]

    if not confirm:
        return {"preview": preview, "total_rows": len(preview), "file_type": file_type, "columns_found": list(best_col.keys())}

    # Save items to DB (markitdown path — xlsx теперь идёт через _save_smart_preview_to_purchase)
    return await _save_smart_preview_to_purchase(pid, preview, purchase, db, current_user, skip_catalog=skip_catalog)

# ---------------------------------------------------------------------------
# PDF Debug endpoint (import-pdf-debug)
# ---------------------------------------------------------------------------

@router.post("/items/import-pdf-debug")
async def import_pdf_debug(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
):
    """Возвращает диагностику парсера для PDF/файла без импорта.

    Полезно для отладки когда Smart Import возвращает 0 строк.
    """
    import io as _io
    content = await file.read()
    result = {
        "filename": file.filename,
        "size_bytes": len(content),
        "pdfplumber_tables": 0,
        "pdfplumber_text_length": 0,
        "ocrmypdf_applied": False,
        "ocrmypdf_available": False,
        "raw_text_preview": "",
        "detected_headers": [],
        "rows_found": 0,
        "errors": [],
    }
    try:
        import pdfplumber
        with pdfplumber.open(_io.BytesIO(content)) as pdf:
            all_tables = []
            all_text = []
            for page in pdf.pages:
                tables = page.extract_tables() or []
                all_tables.extend(tables)
                txt = page.extract_text() or ""
                all_text.append(txt)
            result["pdfplumber_tables"] = len(all_tables)
            full_text = "\n".join(all_text)
            result["pdfplumber_text_length"] = len(full_text)
            result["raw_text_preview"] = full_text[:2000]
            if all_tables and all_tables[0]:
                result["detected_headers"] = [str(c) for c in (all_tables[0][0] or [])]
                result["rows_found"] = sum(max(0, len(t) - 1) for t in all_tables)
    except ImportError:
        result["errors"].append("pdfplumber не установлен")
    except Exception as e:
        result["errors"].append(f"pdfplumber: {type(e).__name__}: {str(e)[:200]}")

    # Если таблиц нет — проверить наличие ocrmypdf
    if result["pdfplumber_tables"] == 0 and result["pdfplumber_text_length"] < 100:
        try:
            import ocrmypdf  # noqa: F401
            result["ocrmypdf_available"] = True
        except ImportError:
            result["ocrmypdf_available"] = False
            result["errors"].append("ocrmypdf не установлен — сканированные PDF не распознаются")

    return result
