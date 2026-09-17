"""Purchase items column-mapped import — extracted from purchase_items_import.py
(Правило №5, разрезание сессии 2026-09-08).

Handles:
  POST /api/purchases/items/import-mapped-nopid  — mapped preview, no purchase yet (wish/new)
  POST /api/purchases/{pid}/items/import-mapped   — mapped import into an existing purchase

Same prefix as purchase_items_import.router ("/api/purchases"); both paths are
at least 2 literal segments longer than purchases.router's catch-all "/{pid}",
so registration order relative to it doesn't matter (see app/routes.py comment
next to purchase_items_import imports). Registered next to
purchase_items_import.router for readability.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
from typing import Optional
from decimal import Decimal
from datetime import datetime

from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.product import Product
from app.services.item_amounts import line_total
from app.auth.jwt import get_current_user, get_single_org_id
from app.models.user import User
from app.services.product_matcher import score as _fuzzy_score, SCORE_AUTO as _SCORE_AUTO
from app.services.feo_plan import assert_tz_not_over_plan
from app.services.product_catalog_match import (
    index_products_by_name, normalize_product_name,
    find_products_by_normalized_names, effective_photo_url,
)
from app.services.items_import_parsing import _extract_html_tables, _read_excel_rows
from app.services.items_import_catalog import _upsert_product_to_catalog, _apply_import_to_existing_product
from app.utils.numbers import to_decimal
from app.services.qty_price_check import check_qty_price_sum, resolve_qty_price_choice
from app.services.request_params import merge_form_over_query
import json as _json

router = APIRouter(prefix="/api/purchases", tags=["purchase-items-import"])

@router.post("/items/import-mapped-nopid")
async def import_items_mapped_nopid(
    file: UploadFile = File(...),
    sheet_name: str = Query(""),
    col_item_name: int = Query(-1),
    col_description: int = Query(-1),
    col_quantity: int = Query(-1),
    col_unit_price: int = Query(-1),
    col_total_price: int = Query(-1),
    col_vat: int = Query(-1),
    col_unit: int = Query(-1),
    col_row_num: Optional[int] = Query(default=None),        # import-vat-cols: № строки (info only)
    col_vat_rate: Optional[int] = Query(default=None),       # import-vat-cols: ставка НДС
    col_vat_amount: Optional[int] = Query(default=None),     # import-vat-cols: сумма НДС
    col_total_with_vat: Optional[int] = Query(default=None), # import-vat-cols: стоимость с НДС
    col_category: Optional[int] = Query(default=None),       # Категория товара
    col_product_type: Optional[int] = Query(default=None),   # Вид товара
    header_row_offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Like import-mapped but for new-purchase/wish context.

    Returns parsed items (не создаёт PurchaseItem). Владелец (2026-09-04): пока
    закупка/заявка не одобрена, в каталог товаров НИЧЕГО не пишем — ни новых
    карточек, ни обновления цены/категории существующих. product_id всегда
    null; категория и вид — как есть в файле (сопоставление с каталогом на
    этом этапе не делается)."""
    if col_item_name < 0:
        raise HTTPException(400, "Не указан столбец Наименование")

    fname = (file.filename or '').lower()
    content = await file.read()

    try:
        if fname.endswith(('.docx', '.doc')):
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
            raw_tables = _extract_html_tables(content, file.filename or fname)
            if not raw_tables:
                raise HTTPException(400, "В HTML не найдено таблиц")
            chosen_rows: list = []
            if sheet_name and sheet_name.lower().startswith('таблица'):
                try:
                    idx = int(sheet_name.split()[-1]) - 1
                    if 0 <= idx < len(raw_tables):
                        chosen_rows = raw_tables[idx]
                except (ValueError, IndexError):
                    pass
            if not chosen_rows:
                chosen_rows = max(raw_tables, key=len)
            all_rows_html = [tuple(row) for row in chosen_rows]
            skip = header_row_offset + 1
            data_iter = all_rows_html[skip:] if len(all_rows_html) > skip else []
        else:
            try:
                sheets = _read_excel_rows(content, fname)
            except Exception as e:
                raise HTTPException(400, f"Не удалось прочитать файл: {e}")
            if not sheets or not sheets[0]:
                raise HTTPException(400, "Файл пустой")
            sheet_idx = 0
            if sheet_name and sheet_name.lower().startswith('лист'):
                try:
                    sheet_idx = int(sheet_name[len('лист'):]) - 1
                except ValueError:
                    pass
            if sheet_idx < 0 or sheet_idx >= len(sheets):
                sheet_idx = 0
            all_rows = sheets[sheet_idx]
            skip = header_row_offset + 1
            data_iter = all_rows[skip:] if len(all_rows) > skip else []
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

    _to_dec = to_decimal

    _SKIP_KEYWORDS_NP = {
        'итого', 'всего', 'итог', 'total', 'подитог', 'subtotal',
        'поставщик', 'покупатель', 'заказчик', 'исполнитель',
        'генеральный директор', 'директор', 'бухгалтер', 'подпись',
        'м.п.', 'м.п', 'печать', 'ооо', 'оао', 'зао', 'ип ',
        'инн', 'кпп', 'огрн', 'р/с', 'к/с', 'бик',
        'адрес', 'телефон', 'email', 'банк',
        'примечание', 'основание', 'договор №', 'счёт №', 'счет №',
    }

    def _is_junk_row_np(name_val: str) -> bool:
        low = name_val.lower().strip()
        for kw in _SKIP_KEYWORDS_NP:
            if low.startswith(kw) or low == kw:
                return True
        if low.startswith('итого'):
            return True
        return False

    items_out = []
    warnings: list[dict] = []
    skipped_empty = 0
    skipped_junk = 0

    for row_num, row in enumerate(data_iter, start=skip + 1):
        item_name = _cell(row, col_item_name)
        if not item_name:
            skipped_empty += 1
            continue
        if _is_junk_row_np(item_name):
            skipped_junk += 1
            continue
        description = _cell(row, col_description) if col_description >= 0 else None
        quantity_raw = _to_dec(_cell(row, col_quantity)) if col_quantity >= 0 else None
        quantity = quantity_raw if quantity_raw else Decimal('1')
        unit_price = _to_dec(_cell(row, col_unit_price)) if col_unit_price >= 0 else None
        total_price = _to_dec(_cell(row, col_total_price)) if col_total_price >= 0 else None
        # Дефект 2 (владелец, 2026-09-14): пока в строке ЕСТЬ все три исходных
        # значения (не после автозаполнения недостающего ниже) — проверяем,
        # что кол-во × цена сходится с суммой из файла; иначе строка попадает
        # в предупреждение с номером строки, а не тихо принимает то, что
        # написано (см. app/services/qty_price_check.py — тот же допуск и
        # текст, что у импорта ФЭО).
        _mismatch = check_qty_price_sum(row_num, item_name, quantity_raw, unit_price, total_price)
        if _mismatch:
            warnings.append(_mismatch)
        unit_raw = _cell(row, col_unit) if col_unit >= 0 else None  # без дефолта — для бэкфилла Product.unit
        unit = unit_raw or 'шт'
        if not total_price and unit_price:
            total_price = line_total(quantity, unit_price)
        elif not unit_price and total_price and quantity:
            unit_price = total_price / quantity
        vat_str = _cell(row, col_vat) if col_vat >= 0 else None
        if vat_str and description:
            description = f"{description} (НДС: {vat_str})"
        elif vat_str:
            description = f"НДС: {vat_str}"
        # import-vat-cols: новые НДС-поля
        vat_rate_str = _cell(row, col_vat_rate) if (col_vat_rate is not None and col_vat_rate >= 0) else None
        vat_amount_dec = _to_dec(_cell(row, col_vat_amount)) if (col_vat_amount is not None and col_vat_amount >= 0) else None
        total_with_vat_dec = _to_dec(_cell(row, col_total_with_vat)) if (col_total_with_vat is not None and col_total_with_vat >= 0) else None

        row_category = _cell(row, col_category) if (col_category is not None and col_category >= 0) else None
        row_product_type = _cell(row, col_product_type) if (col_product_type is not None and col_product_type >= 0) else None

        # Владелец (2026-09-04): «на этапе заявки действительно нет смысла вносить
        # в БД. Вдруг не одобрят». На этом пути закупки/заявки ЕЩЁ НЕТ — в каталог
        # ничего не пишем (ни новых карточек, ни обновления цены/категории у
        # существующих). Категория и вид — как есть в файле, пока не перекрыты
        # ниже сопоставлением с каталогом.
        # Владелец (2026-09-16): «для позиций, которые есть в БД, должны
        # подтягиваться картинки» — product_id/photo_url/описание/ед. изм. для
        # строк с ТОЧНЫМ совпадением имени заполняются пакетно ниже, после
        # цикла (find_products_by_normalized_names — Правило №6, тот же
        # exact-match, что и импорт позиций В закупку, второй матчер не заводим).
        product_id = None
        eff_category, eff_product_type = row_category, row_product_type

        items_out.append({
            'row': row_num,
            'item_name': item_name[:500],
            'item_type': 'товар',
            'description': description,
            'quantity': float(quantity) if quantity else None,
            'unit': unit,
            'unit_price': float(unit_price) if unit_price else None,
            'total_price': float(total_price) if total_price else None,
            'vat_rate': vat_rate_str or (vat_str if not description else None),
            'vat_amount': float(vat_amount_dec) if vat_amount_dec else None,
            'total_with_vat': float(total_with_vat_dec) if total_with_vat_dec else None,
            'product_id': product_id,
            'photo_url': None,
            'category': eff_category,
            'product_type': eff_product_type,
        })

    # Точное сопоставление с каталогом — ТОЛЬКО чтение, ничего не пишем
    # (заявка/закупка ещё не существует). Один батч-запрос на все имена
    # (find_products_by_normalized_names, product_catalog_match.py).
    _names = [it['item_name'] for it in items_out if it['item_name']]
    if _names:
        _matched_by_name = await find_products_by_normalized_names(db, _names)
        for it in items_out:
            _prod = _matched_by_name.get(normalize_product_name(it['item_name']))
            if not _prod:
                continue
            it['product_id'] = _prod.id
            it['photo_url'] = effective_photo_url(_prod)
            if _prod.description and not it['description']:
                it['description'] = _prod.description
            if _prod.unit:
                it['unit'] = _prod.unit

    try:
        await db.commit()
    except Exception:
        await db.rollback()

    return {
        "items": items_out,
        "added": len(items_out),
        "warnings": warnings,
        "debug": {
            "total_rows_after_header": len(data_iter),
            "skipped_empty_name": skipped_empty,
            "skipped_junk_row": skipped_junk,
        },
    }

@router.post("/{pid}/items/import-mapped")
async def import_items_mapped(
    request: Request,
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
    col_row_num: Optional[int] = Query(default=None, description="Индекс столбца № строки (info only)"),
    col_vat_rate: Optional[int] = Query(default=None, description="Индекс столбца Ставка НДС"),
    col_vat_amount: Optional[int] = Query(default=None, description="Индекс столбца Сумма НДС"),
    col_total_with_vat: Optional[int] = Query(default=None, description="Индекс столбца Стоимость с НДС"),
    col_category: Optional[int] = Query(default=None, description="Индекс столбца Категория товара"),
    col_product_type: Optional[int] = Query(default=None, description="Индекс столбца Вид товара"),
    header_row_offset: int = Query(0, description="Сколько строк пропустить до заголовка (авто-определено при preview)"),
    confirm: bool = Query(default=False, description="false — только предпросмотр с предупреждениями, ничего не пишет в БД; true — реальный импорт"),
    resolutions: Optional[str] = Query(default=None, description='JSON {"<row_num>": "recalc_sum"|"recalc_price"|"keep"} — выбор пользователя по строкам с sum_mismatch'),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import items using user-specified column mapping.

    Дефект 2 (владелец, 2026-09-14): «5 шт по 99 990» молча сохранялось
    суммой 499.95 вместо 499 950. Теперь эндпоинт двухфазный, как smart-import:
    confirm=false — парсит файл и возвращает предпросмотр + warnings
    (sum_mismatch с номером строки), НИЧЕГО не пишет в БД; confirm=true —
    применяет resolutions (если пользователь выбрал пересчёт) и импортирует
    по-настоящему. Без warnings в файле поведение как раньше — один вызов
    с confirm=true.

    Тот же дефект, что и HTTP 414 на импорте ФЭО (владелец, 2026-09-17,
    см. app/routers/feo_import.py::import_feo_mapped) — `resolutions` на
    файле с большим числом строк sum_mismatch способен раздуть query-строку.
    Параметры ниже теперь приходят через тело multipart-формы вместе с
    файлом (useItemsImport.ts, _requestMappedImportPid); Query(...) в
    сигнатуре — только обратная совместимость со старым фронтом. Один и
    тот же парсер формы/query, что и у импорта ФЭО (Правило №6, см.
    app/services/request_params.py — второй механизм не заводим)."""
    _p = await merge_form_over_query(
        request,
        dict(
            sheet_name=sheet_name, col_item_name=col_item_name, col_description=col_description,
            col_quantity=col_quantity, col_unit_price=col_unit_price, col_total_price=col_total_price,
            col_vat=col_vat, col_unit=col_unit, col_row_num=col_row_num, col_vat_rate=col_vat_rate,
            col_vat_amount=col_vat_amount, col_total_with_vat=col_total_with_vat, col_category=col_category,
            col_product_type=col_product_type, header_row_offset=header_row_offset, confirm=confirm,
            resolutions=resolutions,
        ),
        bool_fields=frozenset({"confirm"}),
        int_fields=frozenset({
            "col_item_name", "col_description", "col_quantity", "col_unit_price", "col_total_price",
            "col_vat", "col_unit", "col_row_num", "col_vat_rate", "col_vat_amount", "col_total_with_vat",
            "col_category", "col_product_type", "header_row_offset",
        }),
    )
    sheet_name = _p["sheet_name"]
    col_item_name = _p["col_item_name"]
    col_description = _p["col_description"]
    col_quantity = _p["col_quantity"]
    col_unit_price = _p["col_unit_price"]
    col_total_price = _p["col_total_price"]
    col_vat = _p["col_vat"]
    col_unit = _p["col_unit"]
    col_row_num = _p["col_row_num"]
    col_vat_rate = _p["col_vat_rate"]
    col_vat_amount = _p["col_vat_amount"]
    col_total_with_vat = _p["col_total_with_vat"]
    col_category = _p["col_category"]
    col_product_type = _p["col_product_type"]
    header_row_offset = _p["header_row_offset"]
    confirm = _p["confirm"]
    resolutions = _p["resolutions"]

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
            # Use SAME extraction as preview so "Таблица N" indices match.
            raw_tables = _extract_html_tables(content, file.filename or fname)
            if not raw_tables:
                raise HTTPException(400, "В HTML не найдено таблиц")
            chosen_rows: list = []
            if sheet_name and sheet_name.lower().startswith('таблица'):
                try:
                    idx = int(sheet_name.split()[-1]) - 1
                    if 0 <= idx < len(raw_tables):
                        chosen_rows = raw_tables[idx]
                except (ValueError, IndexError):
                    pass
            if not chosen_rows:
                # Fallback: pick the table with the most rows
                chosen_rows = max(raw_tables, key=len)
            # Convert to tuples for uniform downstream handling
            all_rows_html = [tuple(row) for row in chosen_rows]
            skip = header_row_offset + 1
            data_iter = all_rows_html[skip:] if len(all_rows_html) > skip else []
        else:
            try:
                sheets = _read_excel_rows(content, fname)
            except Exception as e:
                raise HTTPException(400, f"Не удалось прочитать файл: {e}")
            if not sheets or not sheets[0]:
                raise HTTPException(400, "Файл пустой")
            # sheet_name здесь — числовой индекс в виде "ЛистN" или первый лист
            sheet_idx = 0
            if sheet_name and sheet_name.lower().startswith('лист'):
                try:
                    sheet_idx = int(sheet_name[len('лист'):]) - 1
                except ValueError:
                    pass
            if sheet_idx < 0 or sheet_idx >= len(sheets):
                sheet_idx = 0
            all_rows = sheets[sheet_idx]
            skip = header_row_offset + 1
            data_iter = all_rows[skip:] if len(all_rows) > skip else []
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

    _to_dec = to_decimal

    def _cell_name(row):
        return _cell(row, col_item_name)

    def _parse_row_numbers(row):
        """Общий разбор кол-во/цена/сумма для превью и для реального импорта
        (Правило №6 — одна логика, не две копии в одном файле)."""
        quantity_raw = _to_dec(_cell(row, col_quantity)) if col_quantity >= 0 else None
        quantity = quantity_raw if quantity_raw else Decimal('1')
        unit_price = _to_dec(_cell(row, col_unit_price)) if col_unit_price >= 0 else None
        total_price = _to_dec(_cell(row, col_total_price)) if col_total_price >= 0 else None
        return quantity_raw, quantity, unit_price, total_price

    try:
        resolutions_map: dict[str, str] = _json.loads(resolutions) if resolutions else {}
    except Exception:
        resolutions_map = {}

    # Keywords that indicate non-product rows (totals, footers, signatures) —
    # определены здесь (а не рядом с основным циклом ниже), т.к. нужны уже в
    # предпросмотре, до основного цикла.
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
        for kw in _SKIP_KEYWORDS:
            if low.startswith(kw) or low == kw:
                return True
        if low.startswith('итого'):
            return True
        return False

    # ── Предпросмотр (confirm=false): парсим файл, считаем warnings по
    # кол-во × цена ≠ сумма, В БД НИЧЕГО НЕ ПИШЕМ — ни PurchaseItem, ни
    # каталог. Дефект 2 (владелец, 2026-09-14): раньше этот эндпоинт всегда
    # коммитил напрямую, расхождение сумм ("5 шт по 99 990" → 499.95 вместо
    # 499 950) уходило в БД молча. ──
    if not confirm:
        preview_items: list[dict] = []
        preview_warnings: list[dict] = []
        _prev_skipped_empty = 0
        _prev_skipped_junk = 0
        for row_num, row in enumerate(data_iter, start=skip + 1):
            item_name = _cell_name(row)
            if not item_name:
                _prev_skipped_empty += 1
                continue
            if _is_junk_row(item_name):
                _prev_skipped_junk += 1
                continue
            quantity_raw, quantity, unit_price, total_price = _parse_row_numbers(row)
            _mismatch = check_qty_price_sum(row_num, item_name, quantity_raw, unit_price, total_price)
            if _mismatch:
                preview_warnings.append(_mismatch)
            preview_items.append({
                'row': row_num,
                'item_name': item_name[:500],
                'quantity': float(quantity) if quantity else None,
                'unit_price': float(unit_price) if unit_price else None,
                'total_price': float(total_price) if total_price else None,
            })
        return {
            "preview": preview_items,
            "warnings": preview_warnings,
            "total_rows": len(preview_items),
            "debug": {
                "total_rows_after_header": len(data_iter),
                "skipped_empty_name": _prev_skipped_empty,
                "skipped_junk_row": _prev_skipped_junk,
            },
        }

    # Load products for auto-matching
    org_id = get_single_org_id(current_user)
    prod_q = select(Product)
    if org_id:
        prod_q = prod_q.where((Product.org_id == org_id) | (Product.org_id.is_(None)))
    prod_result = await db.execute(prod_q)
    products = prod_result.scalars().all()
    # normalize_product_name → предпочтительный Product (Правило №6, при
    # дублях с одинаковым именем предпочитает запись с заполненным описанием).
    product_by_name: dict[str, Product] = index_products_by_name(products)

    added = 0
    matched_catalog = 0
    new_in_catalog = 0
    errors_list = []
    skipped_empty = 0      # row[col_item_name] is None/empty
    skipped_junk = 0       # _is_junk_row matched
    total_data_rows = 0    # счётчик прошедших data_iter

    _user_name = getattr(current_user, 'full_name', None) or getattr(current_user, 'username', '') or ''
    _import_note = (
        f"Импорт из файла «{file.filename}» (маппинг столбцов в закупке), "
        f"{_user_name}, {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

    for row_idx, row in enumerate(data_iter, start=skip + 1):
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
            quantity_raw, quantity, unit_price, total_price = _parse_row_numbers(row)
            # Дефект 2 (владелец, 2026-09-14): выбор пользователя из предпросмотра
            # (recalc_sum/recalc_price/keep) применяется здесь, ДО автозаполнения
            # недостающего значения ниже — molчаливой третьей ветки нет, при
            # отсутствии выбора для строки поведение как раньше (файл как есть).
            _choice = resolutions_map.get(str(row_idx))
            if _choice and _choice != "keep":
                unit_price, total_price = resolve_qty_price_choice(quantity_raw, unit_price, total_price, _choice)
            unit_raw = _cell(row, col_unit) if col_unit >= 0 else None  # без дефолта — для бэкфилла Product.unit
            unit = unit_raw or 'шт'

            # Calculate missing values
            if not total_price and unit_price:
                total_price = line_total(quantity, unit_price)
            elif not unit_price and total_price and quantity:
                unit_price = total_price / quantity

            # Шаг 5 «цена ТЗ не выше плановой» (владелец, 2026-08-07): позиция
            # импорта наследует ФЭО-категорию закупки (feo_planned_item_id импорт
            # не проставляет). Ловим ИМЕННО эту ошибку до общего `except Exception`
            # ниже — тот делает db.rollback(), который стёр бы уже добавленные
            # (ещё не закоммиченные) строки предыдущих итераций; здесь просто
            # пропускаем строку и продолжаем — агрегация ошибок по строкам.
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

            # VAT info → append to description
            vat_str = _cell(row, col_vat) if col_vat >= 0 else None
            if vat_str and description:
                description = f"{description} (НДС: {vat_str})"
            elif vat_str:
                description = f"НДС: {vat_str}"

            # import-vat-cols: новые НДС-поля
            vat_rate_val = _cell(row, col_vat_rate) if (col_vat_rate is not None and col_vat_rate >= 0) else None
            vat_amount_val = _to_dec(_cell(row, col_vat_amount)) if (col_vat_amount is not None and col_vat_amount >= 0) else None
            total_with_vat_val = _to_dec(_cell(row, col_total_with_vat)) if (col_total_with_vat is not None and col_total_with_vat >= 0) else None

            row_category = _cell(row, col_category) if (col_category is not None and col_category >= 0) else None
            row_product_type = _cell(row, col_product_type) if (col_product_type is not None and col_product_type >= 0) else None

            # Auto-match or create in catalog
            # 1) exact match (fast path) — normalize_product_name (Правило №6):
            # обрезка пробелов по краям + схлопывание внутренних + lower().
            matched_product = product_by_name.get(normalize_product_name(item_name))
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
                    total_price = line_total(quantity, unit_price)
                if isinstance(matched_product, Product):
                    # Владелец (2026-09-14): точное совпадение ДОПОЛНЯЕТ товар —
                    # пустые поля из файла, цена НОВОЙ записью в историю цен (не
                    # молча matched_product.price = unit_price, как раньше), не
                    # третья копия правила (Правило №6, см. items_import_catalog.py).
                    await _apply_import_to_existing_product(
                        db, matched_product,
                        unit_price=unit_price, description=description or None,
                        category=row_category, product_type=row_product_type,
                        import_note=_import_note, updated_by=_user_name,
                        unit=unit_raw, user=current_user,
                    )
            else:
                product_id = await _upsert_product_to_catalog(
                    db, item_name, 'товар', unit_price, description or "",
                    category=row_category, product_type=row_product_type,
                    import_note=_import_note, updated_by=_user_name,
                    unit=unit_raw, user=current_user,
                )
                product_by_name[normalize_product_name(item_name)] = type('_P', (), {'id': product_id, 'name': item_name, 'price': unit_price})()
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
                vat_rate=vat_rate_val or vat_str,
                vat_amount=vat_amount_val,
                total_with_vat=total_with_vat_val,
            )
            db.add(item)
            added += 1
        except Exception as e:
            errors_list.append(f"Строка {row_idx}: {e}")
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
