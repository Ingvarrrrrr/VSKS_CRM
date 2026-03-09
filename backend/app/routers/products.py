import os
import shutil
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File, Body
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.product import Product
from app.schemas.schemas import ProductCreate, ProductOut
from typing import List, Optional
from decimal import Decimal
from io import BytesIO
try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None
    load_workbook = None

PRODUCT_UPLOAD_DIR = "/app/uploads/products"
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}

router = APIRouter(prefix="/api/products", tags=["products"])

@router.get("/", response_model=List[ProductOut])
async def list_products(
    feo_category_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    q = select(Product)
    if feo_category_id is not None:
        q = q.where(Product.feo_category_id == feo_category_id)
    if category is not None:
        q = q.where(Product.category == category)
    if is_active is not None:
        q = q.where(Product.is_active == is_active)
    result = await db.execute(q.order_by(Product.name))
    return result.scalars().all()

@router.get("/photos/{filename}")
async def serve_product_photo(filename: str):
    filepath = os.path.join(PRODUCT_UPLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "Файл не найден")
    return FileResponse(filepath)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

def _calc_price_from_links(links: list) -> float | None:
    """Average price using only links from the 3 most recent distinct dates."""
    if not links:
        return None
    # Get all distinct dates that have a price, sorted descending
    dated = [(l.get("collected_at") or "", l["price"]) for l in links if l.get("price") is not None]
    if not dated:
        return None
    top_dates = sorted({d for d, _ in dated if d}, reverse=True)[:3]
    # Include links with no date only if no dated links exist
    if top_dates:
        prices = [p for d, p in dated if d in top_dates]
    else:
        prices = [p for _, p in dated]
    return round(sum(prices) / len(prices), 2) if prices else None


def _apply_price_links(data: dict, target: object) -> None:
    """Auto-calculate price as average of price_links (3 most recent dates)."""
    price = _calc_price_from_links(data.get("price_links") or [])
    if price is not None:
        data["price"] = price

@router.post("/", response_model=ProductOut)
async def create_product(
    product: ProductCreate,
    db: AsyncSession = Depends(get_db)
):
    data = product.model_dump()
    _apply_price_links(data, None)
    db_product = Product(**data)
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product

@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    product: ProductCreate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    db_product = result.scalar_one_or_none()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    data = product.model_dump()
    _apply_price_links(data, db_product)
    for key, value in data.items():
        setattr(db_product, key, value)
    await db.commit()
    await db.refresh(db_product)
    return db_product

@router.patch("/{product_id}", response_model=ProductOut)
async def patch_product(
    product_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Частичное обновление товара (цена, ссылки)."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    db_product = result.scalar_one_or_none()
    if not db_product:
        raise HTTPException(404, "Product not found")
    if "price_links" in data:
        db_product.price_links = data["price_links"]
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(db_product, "price_links")
        # Auto-update price from 3 most recent dates (if not explicitly provided)
        if "price" not in data:
            calc = _calc_price_from_links(data["price_links"])
            if calc is not None:
                db_product.price = Decimal(str(calc))
    if "price" in data:
        db_product.price = Decimal(str(data["price"])) if data["price"] is not None else None
    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    db_product = result.scalar_one_or_none()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.delete(db_product)
    await db.commit()
    return {"message": "Product deleted"}


@router.get("/import/template")
async def download_products_template():
    """Шаблон Excel для импорта товаров."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    wb = Workbook()
    ws = wb.active
    ws.title = "Товары"
    headers = [
        "Наименование", "Описание", "Категория", "Вид",
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
        "Компьютер Dell", "Core i5, 16GB RAM", "Оргтехника", "Рабочая станция",
        "85000", "https://market.yandex.ru/...", "83000", "https://dns-shop.ru/...", "87000", "", "",
        "", "да", "да", "Техническое оснащение",
    ])
    for i, w in enumerate([30, 30, 20, 20, 12, 35, 14, 35, 14, 35, 14, 30, 12, 10, 30], 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "A2"
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=products_template.xlsx"})


@router.post("/import")
async def import_products_from_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Импорт товаров из Excel. Возвращает {created, skipped, errors}."""
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только .xlsx и .xls")

    content = await file.read()
    wb = load_workbook(BytesIO(content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(400, "Файл пустой")

    raw_headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    COLUMN_MAP = {
        "наименование": "name",
        "описание": "description",
        "категория": "category",
        "вид": "product_type",
        "цена": "price",
        "фото (url)": "photo_link",
        "фото": "photo_link",
        "многоразовое": "is_reusable",
        "активен": "is_active",
        "активна": "is_active",
        "категория фэо": "feo_category_name",
    }
    # Also map Ссылка N / Цена ссылки N
    col_idx: dict[str, int] = {}
    for i, h in enumerate(raw_headers):
        field = COLUMN_MAP.get(h)
        if field and field not in col_idx:
            col_idx[field] = i
        # Dynamic link columns
        import re
        m = re.match(r"ссылка (\d+)$", h)
        if m:
            col_idx[f"link_url_{m.group(1)}"] = i
        m2 = re.match(r"цена ссылки (\d+)$", h)
        if m2:
            col_idx[f"link_price_{m2.group(1)}"] = i

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

    created = 0; skipped = 0; errors: list[dict] = []

    for row_num, row in enumerate(rows[1:], start=2):
        try:
            name = cell(row, "name")
            if not name: skipped += 1; continue

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

            p = Product(
                name=name,
                description=cell(row, "description"),
                category=cell(row, "category"),
                product_type=cell(row, "product_type"),
                price=price,
                photo_link=cell(row, "photo_link"),
                is_reusable=to_bool(cell(row, "is_reusable")),
                is_active=to_bool(cell(row, "is_active")),
                feo_category_id=feo_id,
                price_links=price_links or [],
            )
            db.add(p); created += 1
        except Exception as e:
            errors.append({"row": row_num, "name": cell(row, "name") or "?", "message": str(e)})

    await db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}


def _download_and_save_photo(product_id: int, url: str) -> str:
    """Download image from URL, save locally, return local path like /api/products/photos/..."""
    import urllib.request as _ur, tempfile, io as _io
    SUPPORTED = ("image/jpeg", "image/jpg", "image/png", "image/gif", "image/bmp", "image/tiff")
    os.makedirs(PRODUCT_UPLOAD_DIR, exist_ok=True)
    with _ur.urlopen(url, timeout=10) as r:
        ct = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
        raw = r.read()
    is_webp = "webp" in ct or url.lower().endswith(".webp")
    if is_webp:
        from PIL import Image as _Img
        img = _Img.open(_io.BytesIO(raw)).convert("RGB")
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        raw = buf.getvalue()
        ext = ".jpg"
    elif ct in SUPPORTED:
        ext_map = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
                   "image/gif": ".gif", "image/bmp": ".bmp", "image/tiff": ".tiff"}
        ext = ext_map.get(ct, ".jpg")
    else:
        raise ValueError(f"Неподдерживаемый формат: {ct}")
    filename = f"product_{product_id}{ext}"
    dest = os.path.join(PRODUCT_UPLOAD_DIR, filename)
    with open(dest, "wb") as f:
        f.write(raw)
    return f"/api/products/photos/{filename}"


@router.post("/download-photos")
async def download_all_photos(
    db: AsyncSession = Depends(get_db),
):
    """Скачать и сохранить локально фото для всех товаров с URL-ссылками (без локального фото)."""
    import asyncio
    result = await db.execute(select(Product).where(Product.is_active == True))
    all_products = result.scalars().all()

    updated, skipped, errors = 0, 0, []
    for p in all_products:
        # Skip if already has local photo
        if p.photo_url and p.photo_url.startswith("/api/products/photos/"):
            skipped += 1
            continue
        # Find source URL: photo_url (if http) or photo_link
        src = None
        if p.photo_url and (p.photo_url.startswith("http://") or p.photo_url.startswith("https://")):
            src = p.photo_url
        elif p.photo_link and (p.photo_link.startswith("http://") or p.photo_link.startswith("https://")):
            src = p.photo_link
        if not src:
            skipped += 1
            continue
        try:
            local_url = await asyncio.to_thread(_download_and_save_photo, p.id, src)
            p.photo_url = local_url
            updated += 1
        except Exception as e:
            errors.append({"id": p.id, "name": p.name, "error": str(e)})

    if updated:
        await db.commit()
    return {"updated": updated, "skipped": skipped, "errors": errors}


@router.post("/{product_id}/download-photo", response_model=ProductOut)
async def download_single_photo(
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Скачать фото одного товара по его URL-ссылке."""
    import asyncio
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Товар не найден")
    src = None
    if product.photo_url and (product.photo_url.startswith("http://") or product.photo_url.startswith("https://")):
        src = product.photo_url
    elif product.photo_link and (product.photo_link.startswith("http://") or product.photo_link.startswith("https://")):
        src = product.photo_link
    if not src:
        raise HTTPException(400, "Нет URL для скачивания фото")
    try:
        local_url = await asyncio.to_thread(_download_and_save_photo, product.id, src)
        product.photo_url = local_url
        await db.commit()
        await db.refresh(product)
        return product
    except Exception as e:
        raise HTTPException(500, f"Ошибка скачивания: {e}")


@router.post("/{product_id}/photo", response_model=ProductOut)
async def upload_product_photo(
    product_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    if file.content_type not in ALLOWED_IMAGE_MIME:
        raise HTTPException(400, f"Недопустимый тип файла: {file.content_type}")
    os.makedirs(PRODUCT_UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    filename = f"product_{product_id}{ext}"
    dest = os.path.join(PRODUCT_UPLOAD_DIR, filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    product.photo_url = f"/api/products/photos/{filename}"
    await db.commit()
    await db.refresh(product)
    return product