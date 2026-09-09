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
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
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
from app.services.product_unit import backfill_product_unit
from app.services.items_import_parsing import _extract_html_tables, _read_excel_rows
from app.services.items_import_catalog import _upsert_product_to_catalog

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

    def _to_dec(v):
        if v is None:
            return None
        try:
            s = str(v).replace(',', '.').replace(' ', '').replace('\xa0', '')
            import re
            m = re.match(r'^([0-9]+\.?[0-9]*)', s)
            if not m:
                return None
            return Decimal(m.group(1))
        except Exception:
            return None

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
    skipped_empty = 0
    skipped_junk = 0

    for row in data_iter:
        item_name = _cell(row, col_item_name)
        if not item_name:
            skipped_empty += 1
            continue
        if _is_junk_row_np(item_name):
            skipped_junk += 1
            continue
        description = _cell(row, col_description) if col_description >= 0 else None
        quantity = _to_dec(_cell(row, col_quantity)) if col_quantity >= 0 else None
        if not quantity:
            quantity = Decimal('1')
        unit_price = _to_dec(_cell(row, col_unit_price)) if col_unit_price >= 0 else None
        total_price = _to_dec(_cell(row, col_total_price)) if col_total_price >= 0 else None
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
        # существующих). Позиция возвращается с пустым product_id; категория и
        # вид берутся из файла — БД как источник тут недоступна (сопоставления
        # с каталогом на этом этапе не делаем вовсе, в отличие от Smart-импорта,
        # который матчит по имени, но тоже не пишет при отсутствии закупки).
        product_id = None
        eff_category, eff_product_type = row_category, row_product_type

        items_out.append({
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
            'category': eff_category,
            'product_type': eff_product_type,
        })

    try:
        await db.commit()
    except Exception:
        await db.rollback()

    return {
        "items": items_out,
        "added": len(items_out),
        "debug": {
            "total_rows_after_header": len(data_iter),
            "skipped_empty_name": skipped_empty,
            "skipped_junk_row": skipped_junk,
        },
    }

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
    col_row_num: Optional[int] = Query(default=None, description="Индекс столбца № строки (info only)"),
    col_vat_rate: Optional[int] = Query(default=None, description="Индекс столбца Ставка НДС"),
    col_vat_amount: Optional[int] = Query(default=None, description="Индекс столбца Сумма НДС"),
    col_total_with_vat: Optional[int] = Query(default=None, description="Индекс столбца Стоимость с НДС"),
    col_category: Optional[int] = Query(default=None, description="Индекс столбца Категория товара"),
    col_product_type: Optional[int] = Query(default=None, description="Индекс столбца Вид товара"),
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

    _user_name = getattr(current_user, 'full_name', None) or getattr(current_user, 'username', '') or ''
    _import_note = (
        f"Импорт из файла «{file.filename}» (маппинг столбцов в закупке), "
        f"{_user_name}, {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

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
                errors_list.append(f"Строка {row_idx + 1}: {_tz_exc.detail}")
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
                    total_price = line_total(quantity, unit_price)
                elif unit_price and isinstance(matched_product, Product):
                    # Цена из файла актуальнее; категория/вид из БД не трогаем (БД главнее)
                    if matched_product.price != unit_price:
                        matched_product.price = unit_price
                    matched_product.import_note = _import_note
                    matched_product.updated_at = datetime.utcnow()
                    matched_product.updated_by = _user_name
                    if row_category and (not matched_product.category or matched_product.category == 'Прочее'):
                        matched_product.category = row_category
                    if row_product_type and not matched_product.product_type:
                        matched_product.product_type = row_product_type
                if isinstance(matched_product, Product):
                    await backfill_product_unit(db, matched_product, import_unit=unit_raw)
            else:
                product_id = await _upsert_product_to_catalog(
                    db, item_name, 'товар', unit_price, description or "",
                    category=row_category, product_type=row_product_type,
                    import_note=_import_note, updated_by=_user_name,
                    unit=unit_raw,
                )
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
                vat_rate=vat_rate_val or vat_str,
                vat_amount=vat_amount_val,
                total_with_vat=total_with_vat_val,
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
