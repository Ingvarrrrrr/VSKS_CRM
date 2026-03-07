import os
import shutil
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.product import Product
from app.schemas.schemas import ProductCreate, ProductOut
from typing import List, Optional

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

def _apply_price_links(data: dict, target: object) -> None:
    """Auto-calculate price as average of price_links prices."""
    links = data.get("price_links") or []
    prices = [l["price"] for l in links if l.get("price") is not None]
    if prices:
        data["price"] = round(sum(prices) / len(prices), 2)

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