from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.payment import Payment
from app.schemas.schemas import PaymentCreate, PaymentOut
from app.auth.jwt import get_current_user, require_role, MANAGER_ROLES
from app.auth.permissions import require_tab, require_action
from app.services.purchase_payments import recompute_purchase_payments
from typing import List, Optional

router = APIRouter(prefix="/api/payments", tags=["payments"])

@router.get("/", response_model=List[PaymentOut])
async def list_payments(
    contract_id: Optional[int] = Query(None),
    purchase_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),  # read-only — любой авторизованный (employee видит свои закупки)
):
    q = select(Payment)
    if contract_id:
        q = q.where(Payment.contract_id == contract_id)
    if purchase_id:
        q = q.where(Payment.purchase_id == purchase_id)
    result = await db.execute(q.order_by(Payment.payment_date.desc(), Payment.id.desc()))
    return result.scalars().all()

@router.post("/", response_model=PaymentOut)
async def create_payment(data: PaymentCreate, db: AsyncSession = Depends(get_db), _=Depends(require_action('payment.register'))):
    p = Payment(**data.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    if p.purchase_id:
        await recompute_purchase_payments(db, p.purchase_id)
    return p

@router.delete("/{pid}")
async def delete_payment(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_tab('contracts'))):
    result = await db.execute(select(Payment).where(Payment.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    purchase_id = p.purchase_id
    await db.delete(p)
    await db.commit()
    if purchase_id:
        await recompute_purchase_payments(db, purchase_id)
    return {"ok": True}
