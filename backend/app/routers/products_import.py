"""Импорт/экспорт каталога товаров — вынесено из products.py (Правило №5,
сессия 2026-09-08). GET /import/template, POST /import, POST
/bulk-from-purchase-items — литеральные пути, минимум на сегмент длиннее
catch-all "/{product_id}" products.router — по форме не конфликтуют,
регистрируется рядом с остальными products_* соседями для единообразия.
"""
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote as _url_quote

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.import_preview_sheets import detect_header_row, read_preview_sheets, read_full_sheet_rows
from app.services.products_import_map import suggest_products_column_mapping, suggest_products_column_mapping_with_hints
from app.services.products_import_apply import apply_products_import

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


# Ключевые слова для авто-детекта СТРОКИ заголовка (не колонок!) — общие что
# для старого /import (одна активная/лучшая по заполненности книга), что для
# /import-preview (все листы файла).
_PRODUCTS_HEADER_HINTS = (
    'наименован', 'назван', 'товар', 'предмет', 'name', 'title', 'услуг', 'работ',
    'цена', 'описан', 'кол', 'тип', 'price', 'стоимост', 'ед.', 'единиц', 'катег',
)


@router.post("/import")
async def import_products_from_excel(
    file: UploadFile = File(...),
    purchase_id: Optional[int] = Query(None, description="Если передан — добавить импортированные товары в закупку"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Импорт товаров из Excel с автоопределением строки заголовка и ТОЧНЫМ
    (без фаззи-угадывания) сопоставлением колонок из
    services/products_import_map.py — раньше фаззи-цепочка и пере-угадывание
    `name` по типу данных на боевом файле владельца приняли колонку
    «Категория товара» за наименование (план dreamy-booping-piglet.md,
    задача B, дефект №2: 1022 «товара»-категории). Если автоопределение
    промахнулось (в `headers_found` нет `name`) — использовать
    POST /import-preview + POST /import-mapped с ручным маппингом.
    Возвращает {created, updated, skipped, errors, rows, product_ids,
    headers_found, headers_raw}."""
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

    header_row_idx = detect_header_row(rows, _PRODUCTS_HEADER_HINTS)
    rows = rows[header_row_idx:]  # trim leading rows above header

    raw_headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    col_idx = suggest_products_column_mapping(raw_headers)

    result = await apply_products_import(
        db, rows[1:], col_idx,
        filename=file.filename or "", current_user=current_user,
        purchase_id=purchase_id, dry_run=False, first_row_num=2,
    )
    recognized = {field: raw_headers[idx] for field, idx in col_idx.items() if idx < len(raw_headers)}
    return {**result, "headers_found": recognized, "headers_raw": raw_headers[:20]}


@router.post("/import-preview")
async def products_import_preview(
    file: UploadFile = File(...),
    _=Depends(get_current_user),
):
    """Читает Excel/XLS/DOCX/PDF, возвращает ВСЕ листы (заголовки + примеры
    строк, распознанную строку заголовка) и подсказку маппинга колонок
    (`mapping_hint`, только точные совпадения — см. products_import_map.py)
    — БЕЗ применения. Общий сервис чтения с мастером ФЭО
    (services/import_preview_sheets.py, ПРАВИЛО №6). Следующий шаг —
    пользователь подтверждает/правит маппинг и уходит на
    POST /import-mapped с явными индексами колонок."""
    content = await file.read()
    result = read_preview_sheets(content, file.filename or "", _PRODUCTS_HEADER_HINTS)
    for sheet in result["sheets"]:
        # _with_hints — только для превью: точное совпадение + безопасный
        # второй проход (services/products_import_map.py). Старый /import
        # ниже по файлу продолжает звать suggest_products_column_mapping
        # напрямую (без второго прохода) — поведение auto-apply не меняется.
        sheet["mapping_hint"] = suggest_products_column_mapping_with_hints(sheet["headers"])
    return result


@router.post("/import-mapped")
async def products_import_mapped(
    file: UploadFile = File(...),
    sheet_name: str = Query("", description="Имя листа из ответа /import-preview"),
    header_row_offset: int = Query(0, description="Сколько строк пропустить до заголовка (из /import-preview)"),
    dry_run: bool = Query(True, description="true — только посчитать и вернуть отчёт, ничего не сохранять"),
    purchase_id: Optional[int] = Query(None, description="Если передан и dry_run=false — добавить товары в закупку"),
    col_name: int = Query(-1, description="Индекс столбца «Наименование» (0-based, обязателен)"),
    col_description: int = Query(-1),
    col_category: int = Query(-1),
    col_product_type: int = Query(-1),
    col_price: int = Query(-1),
    col_photo_link: int = Query(-1),
    col_is_reusable: int = Query(-1),
    col_is_active: int = Query(-1),
    col_feo_category_name: int = Query(-1),
    col_quantity: int = Query(-1),
    col_unit: int = Query(-1),
    col_link_url_1: int = Query(-1), col_link_price_1: int = Query(-1),
    col_link_url_2: int = Query(-1), col_link_price_2: int = Query(-1),
    col_link_url_3: int = Query(-1), col_link_price_3: int = Query(-1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Импорт с РУЧНЫМ маппингом колонок, подтверждённым после
    POST /import-preview. Индексы колонок — 0-based, из тех же `headers`,
    что вернул предпросмотр для выбранного листа. `dry_run=true` (по
    умолчанию) — построчный отчёт (`rows`: row/action/name/reason) без
    записи в БД; чтобы реально импортировать, передать `dry_run=false`.
    Использует тот же apply_products_import, что и POST /import (ПРАВИЛО
    №6 — поведение импорта не расходится между авто- и ручным маппингом)."""
    if col_name < 0:
        raise HTTPException(400, "Не указан столбец «Наименование»")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только .xlsx и .xls")

    content = await file.read()
    try:
        all_rows = read_full_sheet_rows(content, file.filename or "", sheet_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл ({file.filename}): {e}")

    data_rows = all_rows[header_row_offset + 1:]
    if not data_rows:
        raise HTTPException(400, "Нет строк данных после заголовка")

    col_map_raw = {
        "name": col_name, "description": col_description, "category": col_category,
        "product_type": col_product_type, "price": col_price, "photo_link": col_photo_link,
        "is_reusable": col_is_reusable, "is_active": col_is_active,
        "feo_category_name": col_feo_category_name, "quantity": col_quantity, "unit": col_unit,
        "link_url_1": col_link_url_1, "link_price_1": col_link_price_1,
        "link_url_2": col_link_url_2, "link_price_2": col_link_price_2,
        "link_url_3": col_link_url_3, "link_price_3": col_link_price_3,
    }
    col_idx = {k: v for k, v in col_map_raw.items() if v is not None and v >= 0}

    return await apply_products_import(
        db, data_rows, col_idx,
        filename=file.filename or "", current_user=current_user,
        purchase_id=purchase_id, dry_run=dry_run,
        first_row_num=header_row_offset + 2,
    )


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
