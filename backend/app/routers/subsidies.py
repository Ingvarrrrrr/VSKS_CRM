from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.subsidy import Subsidy
from app.schemas.schemas import SubsidyCreate, SubsidyOut
from app.auth.jwt import get_current_user
from typing import List

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])

@router.get("/", response_model=List[SubsidyOut])
async def list_subsidies(
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).order_by(Subsidy.year.desc(), Subsidy.name))
    return result.scalars().all()

@router.get("/{subsidy_id}", response_model=SubsidyOut)
async def get_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    subsidy = result.scalar_one_or_none()
    if not subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")
    return subsidy

@router.post("/", response_model=SubsidyOut)
async def create_subsidy(
    subsidy: SubsidyCreate,
    db: AsyncSession = Depends(get_db)
):
    db_subsidy = Subsidy(**subsidy.dict())
    db.add(db_subsidy)
    await db.commit()
    await db.refresh(db_subsidy)
    return db_subsidy

@router.put("/{subsidy_id}", response_model=SubsidyOut)
async def update_subsidy(
    subsidy_id: int,
    subsidy: SubsidyCreate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")
    for key, value in subsidy.dict().items():
        setattr(db_subsidy, key, value)
    await db.commit()
    await db.refresh(db_subsidy)
    return db_subsidy

@router.delete("/{subsidy_id}")
async def delete_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")
    await db.delete(db_subsidy)
    await db.commit()
    return {"message": "Subsidy deleted"}