from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.schemas.schemas import PurchaseCreate, PurchaseOut
from app.auth.jwt import get_current_user, require_role
from app.config import settings
from typing import List, Optional
from decimal import Decimal

router = APIRouter(prefix="/api/purchases", tags=["purchases"])

@router.get("/", response_model=List[PurchaseOut])
async def list_purchases(
    contract_id: Optional[int] = Query(None),
    feo_category_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user)
):
    q = select(Purchase)
    if contract_id:
        q = q.where(Purchase.contract_id == contract_id)
    if feo_category_id:
        q = q.where(Purchase.feo_category_id == feo_category_id)
    if status:
        q = q.where(Purchase.status == status)
    result = await db.execute(q.order_by(Purchase.id.desc()))
    return result.scalars().all()

@router.post("/", response_model=PurchaseOut)
async def create_purchase(data: PurchaseCreate, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin", "manager"))):
    # Auto-increment purchase_number
    if not data.purchase_number:
        max_result = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
        data.purchase_number = max_result.scalar() + 1

    # Check subsidy limit
    if data.final_total_amount:
        total_result = await db.execute(
            select(func.coalesce(func.sum(Purchase.final_total_amount), 0))
            .where(Purchase.confirmed == True)
        )
        current_total = total_result.scalar() or Decimal("0")
        if current_total + data.final_total_amount > Decimal(str(settings.SUBSIDY_LIMIT)):
            raise HTTPException(400, f"Превышен лимит субсидии ({settings.SUBSIDY_LIMIT} ₽)")

    p = Purchase(**data.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p

@router.put("/{pid}", response_model=PurchaseOut)
async def update_purchase(pid: int, data: PurchaseCreate, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin", "manager"))):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    return p

@router.delete("/{pid}")
async def delete_purchase(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin"))):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}
