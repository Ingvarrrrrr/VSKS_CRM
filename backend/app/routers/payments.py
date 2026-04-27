from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.payment import Payment
from app.schemas.schemas import PaymentCreate, PaymentOut
from app.auth.jwt import get_current_user, require_role, MANAGER_ROLES
from app.auth.permissions import require_tab, require_action
from typing import List, Optional

router = APIRouter(prefix="/api/payments", tags=["payments"])

@router.get("/", response_model=List[PaymentOut])
async def list_payments(contract_id: Optional[int] = Query(None), db: AsyncSession = Depends(get_db), _=Depends(require_tab('contracts'))):
    q = select(Payment)
    if contract_id:
        q = q.where(Payment.contract_id == contract_id)
    result = await db.execute(q.order_by(Payment.id.desc()))
    return result.scalars().all()

@router.post("/", response_model=PaymentOut)
async def create_payment(data: PaymentCreate, db: AsyncSession = Depends(get_db), _=Depends(require_action('payment.register'))):
    p = Payment(**data.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p

@router.delete("/{pid}")
async def delete_payment(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_tab('contracts'))):
    result = await db.execute(select(Payment).where(Payment.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}
