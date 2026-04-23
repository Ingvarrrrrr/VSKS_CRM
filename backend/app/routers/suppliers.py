from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user, require_role, get_org_filter, get_single_org_id
from app.auth.permissions import require_tab
from app.models.user import User
from app.database import get_db
from app.models.supplier import Supplier, SupplierProduct
from app.schemas.schemas import (
    SupplierCreate, SupplierOut,
    SupplierProductCreate, SupplierProductOut,
)

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.get("/", response_model=List[SupplierOut])
async def list_suppliers(
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Supplier).options(selectinload(Supplier.products)).order_by(Supplier.name)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(Supplier.org_id.in_(org_ids))
    if search:
        q = q.where(Supplier.name.ilike(f"%{search}%"))
    rows = (await db.execute(q)).scalars().all()
    return [_to_supplier_out(s) for s in rows]


@router.post("/", response_model=SupplierOut)
async def create_supplier(
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('contractors')),
):
    d = data.model_dump()
    d['org_id'] = get_single_org_id(current_user) or current_user.org_id
    supplier = Supplier(**d)
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    s = (await db.execute(
        select(Supplier).options(selectinload(Supplier.products)).where(Supplier.id == supplier.id)
    )).scalar_one()
    return _to_supplier_out(s)


@router.put("/{supplier_id}", response_model=SupplierOut)
async def update_supplier(
    supplier_id: int,
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('contractors')),
):
    s = (await db.execute(select(Supplier).where(Supplier.id == supplier_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Поставщик не найден")
    for k, v in data.model_dump().items():
        setattr(s, k, v)
    await db.commit()
    s = (await db.execute(
        select(Supplier).options(selectinload(Supplier.products)).where(Supplier.id == supplier_id)
    )).scalar_one()
    return _to_supplier_out(s)


@router.delete("/{supplier_id}", status_code=204)
async def delete_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('contractors')),
):
    s = (await db.execute(select(Supplier).where(Supplier.id == supplier_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Поставщик не найден")
    await db.delete(s)
    await db.commit()


@router.post("/{supplier_id}/products", response_model=SupplierOut)
async def add_supplier_product(
    supplier_id: int,
    data: SupplierProductCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('contractors')),
):
    s = (await db.execute(select(Supplier).where(Supplier.id == supplier_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Поставщик не найден")
    # Upsert
    existing = (await db.execute(
        select(SupplierProduct).where(
            SupplierProduct.supplier_id == supplier_id,
            SupplierProduct.product_id == data.product_id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.price_notes = data.price_notes
        existing.source = data.source
    else:
        db.add(SupplierProduct(supplier_id=supplier_id, **data.model_dump()))
    await db.commit()
    s = (await db.execute(
        select(Supplier).options(selectinload(Supplier.products)).where(Supplier.id == supplier_id)
    )).scalar_one()
    return _to_supplier_out(s)


@router.delete("/{supplier_id}/products/{product_id}", response_model=SupplierOut)
async def remove_supplier_product(
    supplier_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('contractors')),
):
    sp = (await db.execute(
        select(SupplierProduct).where(
            SupplierProduct.supplier_id == supplier_id,
            SupplierProduct.product_id == product_id,
        )
    )).scalar_one_or_none()
    if not sp:
        raise HTTPException(404, "Связь поставщик-товар не найдена")
    await db.delete(sp)
    await db.commit()
    s = (await db.execute(
        select(Supplier).options(selectinload(Supplier.products)).where(Supplier.id == supplier_id)
    )).scalar_one()
    return _to_supplier_out(s)


def _to_supplier_out(s: Supplier) -> SupplierOut:
    return SupplierOut(
        id=s.id, name=s.name, inn=s.inn, kpp=s.kpp,
        contact=s.contact, phone=s.phone, email=s.email, notes=s.notes,
        products=[
            SupplierProductOut(
                id=p.id, supplier_id=p.supplier_id, product_id=p.product_id,
                price_notes=p.price_notes, source=p.source,
            )
            for p in (s.products or [])
        ],
    )
