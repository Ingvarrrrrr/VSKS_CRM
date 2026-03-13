from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user, require_role
from app.database import get_db
from app.models.product import Product
from app.models.supplier import Supplier, SupplierProduct
from app.schemas.schemas import (
    SupplierCreate,
    SupplierOut,
    SupplierProductOut,
    SupplierProductLinkCreate,
)

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.get("/", response_model=List[SupplierOut])
async def list_suppliers(
    q: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(Supplier).options(selectinload(Supplier.products)).order_by(Supplier.name)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Supplier.name.ilike(like))
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_supplier_out(s) for s in rows]


@router.post("/", response_model=SupplierOut)
async def create_supplier(
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "manager")),
):
    s = Supplier(**data.model_dump())
    db.add(s)
    await db.commit()
    created = (
        await db.execute(
            select(Supplier).options(selectinload(Supplier.products)).where(Supplier.id == s.id)
        )
    ).scalar_one()
    return _to_supplier_out(created)


@router.put("/{supplier_id}", response_model=SupplierOut)
async def update_supplier(
    supplier_id: int,
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "manager")),
):
    s = (await db.execute(select(Supplier).where(Supplier.id == supplier_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Поставщик не найден")
    for k, v in data.model_dump().items():
        setattr(s, k, v)
    await db.commit()

    updated = (
        await db.execute(
            select(Supplier).options(selectinload(Supplier.products)).where(Supplier.id == supplier_id)
        )
    ).scalar_one()
    return _to_supplier_out(updated)


@router.post("/{supplier_id}/products", response_model=SupplierProductOut)
async def link_supplier_product(
    supplier_id: int,
    data: SupplierProductLinkCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "manager")),
):
    s = (await db.execute(select(Supplier).where(Supplier.id == supplier_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Поставщик не найден")

    p = (await db.execute(select(Product).where(Product.id == data.product_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Товар не найден")

    existing = (
        await db.execute(
            select(SupplierProduct)
            .where(SupplierProduct.supplier_id == supplier_id)
            .where(SupplierProduct.product_id == data.product_id)
        )
    ).scalar_one_or_none()

    if existing:
        existing.last_price_note = data.last_price_note
        existing.source = data.source
        await db.commit()
        return _to_supplier_product_out(existing)

    link = SupplierProduct(
        supplier_id=supplier_id,
        product_id=data.product_id,
        last_price_note=data.last_price_note,
        source=data.source,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return _to_supplier_product_out(link)


@router.delete("/{supplier_id}/products/{product_id}")
async def unlink_supplier_product(
    supplier_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "manager")),
):
    row = (
        await db.execute(
            select(SupplierProduct)
            .where(SupplierProduct.supplier_id == supplier_id)
            .where(SupplierProduct.product_id == product_id)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Связь поставщик-товар не найдена")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


def _to_supplier_product_out(x: SupplierProduct) -> SupplierProductOut:
    return SupplierProductOut(
        id=x.id,
        supplier_id=x.supplier_id,
        product_id=x.product_id,
        last_price_note=x.last_price_note,
        source=x.source,
        created_at=x.created_at.isoformat() if x.created_at else None,
    )


def _to_supplier_out(s: Supplier) -> SupplierOut:
    return SupplierOut(
        id=s.id,
        name=s.name,
        inn=s.inn,
        kpp=s.kpp,
        email=s.email,
        phone=s.phone,
        notes=s.notes,
        created_at=s.created_at.isoformat() if s.created_at else None,
        products=[_to_supplier_product_out(x) for x in (s.products or [])],
    )
