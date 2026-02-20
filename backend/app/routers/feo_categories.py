from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.schemas.schemas import FeoCategoryOut, FeoCategoryCreate
from app.auth.jwt import get_current_user
from typing import List, Optional

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])

@router.get("/", response_model=List[FeoCategoryOut])
async def list_categories(
    parent_id: Optional[int] = Query(None),
    level: Optional[int] = Query(None),
    subsidy_id: Optional[int] = Query(None),
    appendix: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    q = select(FeoCategory)
    if parent_id is not None:
        q = q.where(FeoCategory.parent_id == parent_id)
    if level is not None:
        q = q.where(FeoCategory.level == level)
    if subsidy_id is not None:
        q = q.where(FeoCategory.subsidy_id == subsidy_id)
    if appendix is not None:
        q = q.where(FeoCategory.appendix == appendix)
    if is_active is not None:
        q = q.where(FeoCategory.is_active == is_active)
    result = await db.execute(q.order_by(FeoCategory.id))
    return result.scalars().all()

@router.get("/tree")
async def category_tree(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    q = select(FeoCategory)
    if subsidy_id is not None:
        q = q.where(FeoCategory.subsidy_id == subsidy_id)
    result = await db.execute(q.order_by(FeoCategory.level, FeoCategory.id))
    all_cats = result.scalars().all()
    by_id = {c.id: {"id": c.id, "parent_id": c.parent_id, "subsidy_id": c.subsidy_id,
                    "level": c.level, "name": c.name, "code": c.code, 
                    "appendix": c.appendix, "is_active": c.is_active,
                    "children": []} for c in all_cats}
    roots = []
    for c in all_cats:
        node = by_id[c.id]
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots

@router.post("/", response_model=FeoCategoryOut)
async def create_category(
    category_data: FeoCategoryCreate,
    db: AsyncSession = Depends(get_db)
):
    # Проверяем, существует ли родительская категория
    if category_data.parent_id:
        parent_result = await db.execute(
            select(FeoCategory).where(FeoCategory.id == category_data.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Родительская категория не найдена"
            )
        # Устанавливаем уровень на 1 больше, чем у родителя
        level = parent.level + 1
        if level > 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Максимальный уровень вложенности - 3"
            )
    else:
        # Если нет родителя, это корневая категория (уровень 1)
        level = 1
    
    # Создаем новую категорию
    new_category = FeoCategory(
        parent_id=category_data.parent_id,
        subsidy_id=category_data.subsidy_id,
        level=level,
        name=category_data.name,
        code=category_data.code,
        appendix=category_data.appendix,
        is_active=category_data.is_active
    )
    
    db.add(new_category)
    await db.commit()
    await db.refresh(new_category)
    
    return new_category
