from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.contractor import Contractor
from app.schemas.schemas import ContractorCreate, ContractorOut
from app.auth.jwt import get_current_user, require_role
from typing import List

router = APIRouter(prefix="/api/contractors", tags=["contractors"])

@router.get("/", response_model=List[ContractorOut])
async def list_contractors(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contractor).order_by(Contractor.name))
    return result.scalars().all()

@router.post("/", response_model=ContractorOut)
async def create_contractor(data: ContractorCreate, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin", "manager"))):
    c = Contractor(**data.model_dump())
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c

@router.put("/{cid}", response_model=ContractorOut)
async def update_contractor(cid: int, data: ContractorCreate, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin", "manager"))):
    result = await db.execute(select(Contractor).where(Contractor.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    await db.commit()
    await db.refresh(c)
    return c

@router.delete("/{cid}")
async def delete_contractor(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin"))):
    result = await db.execute(select(Contractor).where(Contractor.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    await db.delete(c)
    await db.commit()
    return {"ok": True}
