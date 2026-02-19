from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.schemas.schemas import FeoCategoryOut
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
