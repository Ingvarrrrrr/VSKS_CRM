from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.schemas.schemas import SubsidyCreate, SubsidyOut
from app.auth.jwt import get_current_user
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])

class SubsidyOut(BaseModel):
    id: int
    name: str
    year: int
    budget: float
    description: Optional[str] = None
    calculated_budget: Optional[float] = None
    model_config = {"from_attributes": True}

async def calculate_budget_from_categories(db: AsyncSession, subsidy_id: int) -> float:
    """Подсчёт бюджета из дочерних категорий (рекурсивно)"""
    total = 0.0
    
    # Получаем все категории субсидии
    result = await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    ).scalars().all()
    
    # Создаём словарь для подсчёта
    categories = {c.id: c for c in result}
    
    def get_budget(cat_id: int) -> float:
        cat = categories.get(cat_id)
        if not cat:
            return 0.0
        # Если есть ручной бюджет - используем его
        if cat.budget is not None:
            return float(cat.budget)
        # Иначе суммируем детей
        children = [c for c in result if c.parent_id == cat_id]
        if not children:
            return 0.0
        return sum(get_budget(c.id) for c in children)
    
    # Считаем только для верхнего уровня (level=1)
    top_level = [c for c in result if c.level == 1]
    for cat in top_level:
        total += get_budget(cat.id)
    
    return total

@router.get("/", response_model=List[SubsidyOut])
async def list_subsidies(
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).order_by(Subsidy.year.desc(), Subsidy.name))
    subsidies = result.scalars().all()
    
    # Добавляем calculated_budget
    output = []
    for s in subsidies:
        calc = calculate_budget_from_categories(db, s.id)
        output.append(SubsidyOut(
            id=s.id,
            name=s.name,
            year=s.year,
            budget=s.budget,
            description=s.description,
            calculated_budget=calc
        ))
    return output

@router.get("/{subsidy_id}", response_model=SubsidyOut)
async def get_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    subsidy = result.scalar_one_or_none()
    if not subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")
    
    calc = calculate_budget_from_categories(db, subsidy_id)
    return SubsidyOut(
        id=subsidy.id,
        name=subsidy.name,
        year=subsidy.year,
        budget=subsidy.budget,
        description=subsidy.description,
        calculated_budget=calc
    )

@router.post("/", response_model=SubsidyOut)
async def create_subsidy(
    subsidy: SubsidyCreate,
    db: AsyncSession = Depends(get_db)
):
    db_subsidy = Subsidy(**subsidy.dict())
    db.add(db_subsidy)
    await db.commit()
    await db.refresh(db_subsidy)
    return SubsidyOut(
        id=db_subsidy.id,
        name=db_subsidy.name,
        year=db_subsidy.year,
        budget=db_subsidy.budget,
        description=db_subsidy.description,
        calculated_budget=None
    )

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
    calc = calculate_budget_from_categories(db, subsidy_id)
    return SubsidyOut(
        id=db_subsidy.id,
        name=db_subsidy.name,
        year=db_subsidy.year,
        budget=db_subsidy.budget,
        description=db_subsidy.description,
        calculated_budget=calc
    )

@router.delete("/{subsidy_id}")
async def delete_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    from app.models.purchase import Purchase
    p_count = await db.scalar(
        select(Purchase).where(Purchase.subsidy_id == subsidy_id).limit(1)
    )
    if p_count:
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить субсидию: есть связанные закупки. Сначала удалите или перенесите их."
        )

    from sqlalchemy import text
    await db.execute(text("DELETE FROM wishes WHERE subsidy_id = :sid"), {"sid": subsidy_id})

    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(FeoCategory.level.desc())
    )).scalars().all()
    for cat in cats:
        await db.delete(cat)

    await db.delete(db_subsidy)
    await db.commit()
    return {"message": "Субсидия удалена"}
