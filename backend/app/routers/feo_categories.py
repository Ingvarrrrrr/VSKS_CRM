from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.schemas.schemas import FeoCategoryOut, FeoCategoryCreate
from app.auth.jwt import get_current_user
from typing import List, Optional

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


@router.get("/purchase-totals")
async def get_purchase_totals(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Sum of planned_total_price per feo_category_id for a given subsidy."""
    from app.models.purchase import Purchase
    stmt = (
        select(
            Purchase.feo_category_id,
            func.coalesce(func.sum(Purchase.planned_total_price), 0).label("total_planned"),
        )
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.feo_category_id.isnot(None))
        .group_by(Purchase.feo_category_id)
    )
    rows = (await db.execute(stmt)).all()
    return {r.feo_category_id: float(r.total_planned) for r in rows}


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
                    "budget": float(c.budget) if c.budget is not None else None,
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
    if category_data.parent_id:
        parent_result = await db.execute(
            select(FeoCategory).where(FeoCategory.id == category_data.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Родительская категория не найдена")
        level = parent.level + 1
        if level > 3:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Максимальный уровень вложенности - 3")
    else:
        level = 1

    new_category = FeoCategory(
        parent_id=category_data.parent_id,
        subsidy_id=category_data.subsidy_id,
        level=level,
        name=category_data.name,
        code=category_data.code,
        appendix=category_data.appendix,
        is_active=category_data.is_active,
        budget=category_data.budget,
    )
    db.add(new_category)
    await db.commit()
    await db.refresh(new_category)
    return new_category


@router.put("/{cat_id}", response_model=FeoCategoryOut)
async def update_category(
    cat_id: int,
    category_data: FeoCategoryCreate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    cat.name = category_data.name
    cat.code = category_data.code
    cat.appendix = category_data.appendix
    cat.is_active = category_data.is_active
    cat.budget = category_data.budget
    await db.commit()
    await db.refresh(cat)
    return cat


@router.delete("/{cat_id}")
async def delete_category(
    cat_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    # Check children
    children = (await db.execute(
        select(FeoCategory).where(FeoCategory.parent_id == cat_id).limit(1)
    )).scalar_one_or_none()
    if children:
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить категорию: есть дочерние направления. Сначала удалите их."
        )

    # Check linked purchases
    from app.models.purchase import Purchase
    linked = (await db.execute(
        select(Purchase).where(Purchase.feo_category_id == cat_id).limit(1)
    )).scalar_one_or_none()
    if linked:
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить категорию: есть связанные закупки."
        )

    await db.delete(cat)
    await db.commit()
    return {"ok": True}
