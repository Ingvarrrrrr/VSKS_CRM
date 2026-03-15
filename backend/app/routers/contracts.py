from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.contract import Contract
from app.models.purchase import Purchase
from app.schemas.schemas import ContractCreate, ContractOut
from app.auth.jwt import get_current_user, require_role, get_org_filter
from app.models.subsidy import Subsidy
from typing import List, Optional
from decimal import Decimal

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

@router.get("/", response_model=List[ContractOut])
async def list_contracts(
    subsidy_id: Optional[int] = Query(None),
    contract_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = select(Contract).options(selectinload(Contract.contractor)).order_by(Contract.id.desc())
    if subsidy_id is not None:
        q = q.where(Contract.subsidy_id == subsidy_id)
    if contract_type is not None:
        q = q.where(Contract.contract_type == contract_type)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.join(Subsidy, Contract.subsidy_id == Subsidy.id).where(Subsidy.org_id.in_(org_ids))
    result = await db.execute(q)
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
        if c.contractor:
            d.contractor_name = c.contractor.name
            d.contractor_inn = c.contractor.inn
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
