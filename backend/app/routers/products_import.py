"""Импорт/экспорт каталога товаров — вынесено из products.py (Правило №5,
сессия 2026-09-08). GET /import/template, POST /import, POST
/bulk-from-purchase-items — литеральные пути, минимум на сегмент длиннее
catch-all "/{product_id}" products.router — по форме не конфликтуют,
регистрируется рядом с остальными products_* соседями для единообразия.
"""
from decimal import Decimal
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote as _url_quote

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.product import Product
from app.models.user import User
from app.services.price_actualization import actualize_product_price
from app.services.product_unit import backfill_product_unit

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None
    load_workbook = None

try:
    import xlrd as _xlrd
except ImportError:
    _xlrd = None


def _read_excel_rows(content: bytes, filename: str):
    """Read rows from xlsx or xls file. Returns list of tuples (best sheet)."""
    if filename.lower().endswith(".xls"):
        if _xlrd is None:
            raise HTTPException(500, "xlrd не установлен")
        wb = _xlrd.open_workbook(file_contents=content)
        # Pick the sheet with the most non-empty rows
        best_sheet = wb.sheet_by_index(0)
        best_count = sum(1 for i in range(best_sheet.nrows) if any(v for v in best_sheet.row_values(i)))
        for si in range(1, wb.nsheets):
            sh = wb.sheet_by_index(si)
            cnt = sum(1 for i in range(sh.nrows) if any(v for v in sh.row_values(i)))
            if cnt > best_count:
                best_count = cnt
                best_sheet = sh
        return [tuple(best_sheet.row_values(i)) for i in range(best_sheet.nrows)]
    else:
        if load_workbook is None:
            raise HTTPException(500, "openpyxl не установлен")
        wb = load_workbook(BytesIO(content), data_only=True)
        ws = wb.active
        return list(ws.iter_rows(values_only=True))


router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/import/template")
async def download_products_template(
    _=Depends(get_current_user),
):
    """Шаблон Excel для импорта товаров."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    wb = Workbook()
    ws = wb.active
    ws.title = "Товары"
    headers = [
        "Наименование", "Описание", "Категория", "Вид", "Ед. изм.",
        "Цена", "Ссылка 1", "Цена ссылки 1", "Ссылка 2", "Цена ссылки 2", "Ссылка 3", "Цена ссылки 3",
        "Фото (URL)", "Многоразовое", "Активен", "Категория ФЭО",
    ]
    ws.append(headers)
    fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    font = Font(color="FFFFFF", bold=True, size=11)
    for cell in ws[1]:
        cell.fill = fill; cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.append([
        "Компьютер Dell", "Core i5, 16GB RAM", "Оргтехника", "Рабочая станция", "шт",
        "85000", "https://market.yandex.ru/...", "83000", "https://dns-shop.ru/...", "87000", "", "",
        "", "да", "да", "Техническое оснащение",
    ])
    for i, w in enumerate([30, 30, 20, 20, 10, 12, 35, 14, 35, 14, 35, 14, 30, 12, 10, 30], 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "A2"
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_url_quote('Шаблон_импорта_товаров.xlsx', safe='-_.~')}"})


@router.post("/import")
async def import_products_from_excel(
    file: UploadFile = File(...),
    purchase_id: Optional[int] = Query(None, description="Если передан — добавить импортированные товары в закупку"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Импорт товаров из Excel. Возвращает {created, skipped, errors}."""
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только .xlsx и .xls")

    content = await file.read()
    try:
        rows = _read_excel_rows(content, file.filename or "")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Не удалось прочитать файл. Убедитесь, что файл не повреждён.")
    if len(rows) < 2:
        raise HTTPException(400, "Файл пустой")

    # Auto-detect header row — scan ALL rows for the one with most recognizable column names
    NAME_HINTS = ('наименован', 'назван', 'товар', 'предмет', 'name', 'title', 'услуг', 'работ')
    ALL_HINTS = NAME_HINTS + ('цена', 'описан', 'кол', 'тип', 'price', 'стоимост', 'ед.', 'единиц', 'катег')
    header_row_idx = 0
    best_score = 0
    for ri, row in enumerate(rows):
        norm = [str(h).strip().lower() if h is not None else "" for h in row]
        score = sum(1 for h in norm if h and any(x in h for x in ALL_HINTS))
        if score > best_score:
            best_score = score
            header_row_idx = ri
    rows = rows[header_row_idx:]  # trim leading rows above header

    raw_headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    COLUMN_MAP = {
        "наименование": "name",
        "название": "name",
        "наименование товара": "name",
        "товар": "name",
        "name": "name",
        "описание": "description",
        "description": "description",
        "категория": "category",
        "category": "category",
        "вид": "product_type",
        "тип": "product_type",
        "type": "product_type",
        "цена": "price",
        "цена, руб": "price",
        "цена, ₽": "price",
        "цена (руб)": "price",
        "стоимость": "price",
        "price": "price",
        "фото (url)": "photo_link",
        "фото": "photo_link",
        "photo": "photo_link",
        "ссылка на фото": "photo_link",
        "многоразовое": "is_reusable",
        "активен": "is_active",
        "активна": "is_active",
        "active": "is_active",
        "категория фэо": "feo_category_name",
        "фэо": "feo_category_name",
        "направление фэо": "feo_category_name",
    }
    # Also map Ссылка N / Цена ссылки N
    import re as _re
    col_idx: dict[str, int] = {}
    for i, h in enumerate(raw_headers):
        # Exact match first
        field = COLUMN_MAP.get(h)
        if field and field not in col_idx:
            col_idx[field] = i
        # Fuzzy/partial match for name and common fields
        if 'name' not in col_idx and any(x in h for x in ('наименован', 'назван', 'товар', 'предмет', 'наимен')):
            col_idx['name'] = i
        elif 'description' not in col_idx and any(x in h for x in ('описан', 'техническ', 'характерист', 'specification')):
            col_idx['description'] = i
        elif 'price' not in col_idx and any(x in h for x in ('цена', 'стоимость', 'price')) and 'сумм' not in h:
            col_idx['price'] = i
        elif 'product_type' not in col_idx and any(x in h for x in ('тип', 'вид', 'type')):
            col_idx['product_type'] = i
        elif 'category' not in col_idx and 'категор' in h:
            col_idx['category'] = i
        elif 'quantity' not in col_idx and any(x in h for x in ('кол-во', 'количеств', 'qty', 'кол.')):
            col_idx['quantity'] = i
        elif 'unit' not in col_idx and any(x in h for x in ('ед.', 'ед. изм', 'единиц', 'unit')):
            col_idx['unit'] = i
        # Dynamic link columns
        m = _re.match(r"ссылка (\d+)$", h)
        if m:
            col_idx[f"link_url_{m.group(1)}"] = i
        m2 = _re.match(r"цена ссылки (\d+)$", h)
        if m2:
            col_idx[f"link_price_{m2.group(1)}"] = i

    # Post-map validation: if 'name' column contains numbers in data rows,
    # find the first string-heavy column instead (handles article+name dual-column files)
    if 'name' in col_idx and len(rows) > 1:
        name_col = col_idx['name']
        sample_vals = [rows[i][name_col] for i in range(1, min(4, len(rows))) if name_col < len(rows[i])]
        numeric_count = sum(1 for v in sample_vals if isinstance(v, (int, float)) and v == v)
        if numeric_count >= len(sample_vals) and sample_vals:
            # Mapped name column has only numbers — find the first string column
            for ci in range(len(rows[0])):
                if ci == name_col:
                    continue
                str_vals = [rows[i][ci] for i in range(1, min(4, len(rows))) if ci < len(rows[i])]
                if sum(1 for v in str_vals if isinstance(v, str) and len(v.strip()) > 5) >= len(str_vals) // 2 + 1:
                    col_idx['name'] = ci
                    break

    # FEO lookup
    from app.models.feo_category import FeoCategory
    feo_rows = (await db.execute(select(FeoCategory))).scalars().all()
    feo_by_name = {f.name.lower().strip(): f.id for f in feo_rows}

    def cell(row, field):
        idx = col_idx.get(field)
        if idx is None or idx >= len(row): return None
        v = row[idx]; return str(v).strip() if v is not None else None

    def to_bool(v):
        if v is None: return True
        return str(v).lower().strip() in ("да", "yes", "true", "1", "+")

    def to_dec(v):
        if v is None: return None
        try: return Decimal(str(v).replace(" ", "").replace(",", "."))
        except: return None

    # Load existing products for dedup check (key → Product)
    def _norm_key(s) -> str:
        return (s or '').replace('\r\n', '\n').replace('\r', '\n').strip().lower()

    existing_result = await db.execute(select(Product))
    existing_by_key: dict[str, Product] = {}
    for ep in existing_result.scalars().all():
        k = _norm_key(ep.name) + '|' + _norm_key(ep.description)
        existing_by_key[k] = ep

    created = 0; skipped = 0; errors: list[dict] = []
    all_products: list[Product] = []   # both new and existing (for purchase items)
    product_row_data: list[dict] = []  # qty/unit per product for PurchaseItem

    from datetime import datetime as _dt
    _user_name = getattr(current_user, 'full_name', None) or getattr(current_user, 'username', '') or ''
    _import_note = (
        f"Импорт каталога из файла «{file.filename}», "
        f"{_user_name}, {_dt.now().strftime('%d.%m.%Y %H:%M')}"
    )

    for row_num, row in enumerate(rows[1:], start=2):
        try:
            name = cell(row, "name")
            if not name: continue  # empty row — don't count as skipped product
            desc_val = cell(row, "description")
            dedup_key = _norm_key(name) + '|' + _norm_key(desc_val)

            # Collect price_links
            price_links = []
            for n in range(1, 10):
                url = cell(row, f"link_url_{n}")
                if not url: break
                price_val = to_dec(cell(row, f"link_price_{n}"))
                price_links.append({"url": url, "price": float(price_val) if price_val else None})

            feo_name = cell(row, "feo_category_name")
            feo_id = feo_by_name.get(feo_name.lower().strip()) if feo_name else None

            price = to_dec(cell(row, "price"))
            if not price and price_links:
                prices = [l["price"] for l in price_links if l["price"]]
                if prices: price = Decimal(str(round(sum(prices) / len(prices), 2)))

            qty_str = cell(row, "quantity")
            unit_raw = cell(row, "unit")  # без дефолта — для бэкфилла Product.unit
            unit_str = unit_raw or "шт."
            row_qty = None
            if qty_str:
                try: row_qty = Decimal(str(qty_str).replace(',', '.').replace(' ', ''))
                except: pass

            if dedup_key in existing_by_key:
                # Product already in catalog — update price + backfill empty fields
                ep = existing_by_key[dedup_key]
                if price and ep.price != price:
                    # Актуализация цены (владелец, 2026-08-29): цена пришла из
                    # импортируемого Excel-файла — source='import'.
                    await actualize_product_price(
                        db, ep, price=price, source="import",
                        source_ref=file.filename, user=current_user,
                    )

                # Fill ONLY empty string-fields on existing product from this row
                def _fill(attr, val):
                    if val and not getattr(ep, attr):
                        setattr(ep, attr, val)

                # Категория: «Прочее» — дефолт, считаем пустым; заполненную в БД не трогаем (БД главнее)
                if cell(row, "category") and (not ep.category or ep.category == 'Прочее'):
                    ep.category = cell(row, "category")
                _fill("product_type", cell(row, "product_type"))
                _fill("photo_link", cell(row, "photo_link"))
                _fill("description", cell(row, "description"))

                ep.import_note = _import_note
                ep.updated_at = _dt.utcnow()
                ep.updated_by = _user_name

                # feo_category_id — numeric, set only if empty
                if feo_id and not ep.feo_category_id:
                    ep.feo_category_id = feo_id

                # price_links — list, fill only if existing empty and new non-empty
                if price_links and not ep.price_links:
                    from sqlalchemy.orm.attributes import flag_modified
                    ep.price_links = price_links
                    flag_modified(ep, "price_links")

                # Единица измерения (владелец, 2026-09-01): не трогаем уже
                # заполненную; иначе — из самого импорта, иначе — из истории
                # закупок этого товара (единственная встречавшаяся).
                await backfill_product_unit(db, ep, import_unit=unit_raw)

                all_products.append(ep)
                product_row_data.append({"qty": row_qty, "unit": unit_str, "price": price or ep.price})
                skipped += 1
                continue

            p = Product(
                name=name,
                description=cell(row, "description"),
                category=cell(row, "category"),
                product_type=cell(row, "product_type"),
                unit=(unit_raw or "").strip() or None,  # брэнд-новый товар — истории покупок ещё нет
                price=price,
                photo_link=cell(row, "photo_link"),
                is_reusable=to_bool(cell(row, "is_reusable")),
                is_active=to_bool(cell(row, "is_active")),
                feo_category_id=feo_id,
                price_links=price_links or [],
                import_note=_import_note,
                updated_at=_dt.utcnow(),
                updated_by=_user_name,
            )
            db.add(p)
            all_products.append(p)
            product_row_data.append({"qty": row_qty, "unit": unit_str, "price": price})
            created += 1
        except Exception as e:
            errors.append({"row": row_num, "name": cell(row, "name") or "?", "message": str(e)})

    # Flush to get product IDs
    await db.flush()

    product_ids: list[int] = [p.id for p in all_products]

    # If purchase_id provided — add ALL products (new + existing) as purchase items
    if purchase_id and all_products:
        from app.models.purchase_item import PurchaseItem
        for idx_p, p in enumerate(all_products):
            rd = product_row_data[idx_p] if idx_p < len(product_row_data) else {}
            qty = rd.get("qty") or Decimal('1')
            unit = rd.get("unit") or 'шт.'
            unit_price = rd.get("price") or p.price
            total = (qty * unit_price) if unit_price else None
            db.add(PurchaseItem(
                purchase_id=purchase_id,
                product_id=p.id,
                item_name=p.name[:500],
                item_type=p.product_type or 'товар',
                quantity=qty,
                unit=unit,
                unit_price=unit_price,
                total_price=total,
            ))

    await db.commit()
    recognized = {field: raw_headers[idx] for field, idx in col_idx.items()}
    return {"created": created, "skipped": skipped, "errors": errors,
            "product_ids": product_ids,
            "headers_found": recognized, "headers_raw": raw_headers[:20]}


# import-no-clutter: bulk-add purchase items to catalog
class _BulkFromItemsRequest(BaseModel):
    purchase_item_ids: List[int]


@router.post("/bulk-from-purchase-items")
async def bulk_create_from_items(
    body: _BulkFromItemsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Массовое создание Product из несвязанных PurchaseItem'ов.

    Для каждого PurchaseItem с product_id=None создаёт или находит Product
    через _upsert_product_to_catalog (идемпотентно).
    Обновляет item.product_id, match_confirmed=True.
    Returns: {created: int, linked: int, errors: list}
    """
    from app.models.purchase_item import PurchaseItem
    from app.routers.purchase_items_import import _upsert_product_to_catalog

    created = 0
    linked = 0
    errors: list[str] = []

    for item_id in body.purchase_item_ids:
        try:
            item = await db.get(PurchaseItem, item_id)
            if not item:
                errors.append(f"PurchaseItem {item_id} не найден")
                continue
            if item.product_id is not None:
                linked += 1
                continue
            from datetime import datetime as _dtb
            _uname = getattr(current_user, 'full_name', None) or getattr(current_user, 'username', '') or ''
            product_id = await _upsert_product_to_catalog(
                db, item.item_name, item.item_type or "товар", item.unit_price,
                import_note=f"Добавлен из позиций закупки (сопоставление), {_uname}, {_dtb.now().strftime('%d.%m.%Y %H:%M')}",
                updated_by=_uname,
            )
            item.product_id = product_id
            item.match_confirmed = True
            created += 1
        except Exception as e:
            errors.append(f"item {item_id}: {e}")

    try:
        await db.commit()
    except Exception as e:
        raise HTTPException(500, f"Ошибка сохранения: {e}")

    return {"created": created, "linked": linked, "errors": errors}
