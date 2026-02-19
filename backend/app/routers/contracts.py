from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.contract import Contract
from app.models.purchase import Purchase
from app.schemas.schemas import ContractCreate, ContractOut
from app.auth.jwt import get_current_user, require_role
from typing import List
from decimal import Decimal

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

@router.get("/", response_model=List[ContractOut])
async def list_contracts(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Contract).order_by(Contract.id.desc()))
    contracts = result.scalars().all()
    out = []
    for c in contracts:
        pay_result = await db.execute(
            select(func.coalesce(func.sum(Purchase.delivery_payment_amount), 0))
            .where(Purchase.contract_id == c.id)
        )
        total_payment = pay_result.scalar() or Decimal("0")
        d = ContractOut.model_validate(c)
        d.total_payment = total_payment
        d.remaining = (c.max_amount or Decimal("0")) - total_payment
        out.append(d)
    return out

@router.post("/", response_model=ContractOut)
async def create_contract(data: ContractCreate, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin", "manager"))):
    c = Contract(**data.model_dump())
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return ContractOut.model_validate(c)

@router.put("/{cid}", response_model=ContractOut)
async def update_contract(cid: int, data: ContractCreate, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin", "manager"))):
    result = await db.execute(select(Contract).where(Contract.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    await db.commit()
    await db.refresh(c)
    return ContractOut.model_validate(c)

@router.delete("/{cid}")
async def delete_contract(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin"))):
    result = await db.execute(select(Contract).where(Contract.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    await db.delete(c)
    await db.commit()
    return {"ok": True}
