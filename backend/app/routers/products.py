from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.product import Product
from app.schemas.schemas import ProductCreate, ProductOut
from typing import List, Optional

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

@router.post("/", response_model=ProductOut)
async def create_product(
    product: ProductCreate,
    db: AsyncSession = Depends(get_db)
):
    db_product = Product(**product.dict())
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
    for key, value in product.dict().items():
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