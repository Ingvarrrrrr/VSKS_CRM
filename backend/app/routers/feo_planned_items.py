from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, require_role, ADMIN_ROLES
from app.database import get_db
from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_category import FeoCategory
from app.models.purchase_item import PurchaseItem
from app.models.purchase import Purchase
from app.schemas.schemas import FeoPlannedItemCreate, FeoPlannedItemOut, FeoComparisonOut, FeoActualItemOut

router = APIRouter(prefix="/api/feo-planned-items", tags=["feo_planned_items"])


@router.get("/", response_model=List[FeoPlannedItemOut])
async def list_planned_items(
    feo_category_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    rows = (await db.execute(
        select(FeoPlannedItem)
        .where(FeoPlannedItem.feo_category_id == feo_category_id)
        .order_by(FeoPlannedItem.id)
    )).scalars().all()
    return rows


@router.post("/", response_model=FeoPlannedItemOut)
async def create_planned_item(
    data: FeoPlannedItemCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    cat = (await db.execute(
        select(FeoCategory).where(FeoCategory.id == data.feo_category_id)
    )).scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Категория ФЭО не найдена")

    item = FeoPlannedItem(
        feo_category_id=data.feo_category_id,
        name=data.name,
        quantity=data.quantity,
        unit=data.unit,
        amount=data.amount,
        notes=data.notes,
        is_active=data.is_active,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/{item_id}", response_model=FeoPlannedItemOut)
async def update_planned_item(
    item_id: int,
    data: FeoPlannedItemCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    item = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.id == item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Плановая позиция не найдена")
    item.name = data.name
    item.quantity = data.quantity
    item.unit = data.unit
    item.amount = data.amount
    item.notes = data.notes
    item.is_active = data.is_active
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}")
async def delete_planned_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    item = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.id == item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Плановая позиция не найдена")
    await db.delete(item)
    await db.commit()
    return {"ok": True}


@router.post("/map")
async def map_purchase_item_to_planned(
    purchase_item_id: int,
    planned_item_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    """Сопоставить purchase_item с плановой позицией. planned_item_id=null — снять сопоставление."""
    pi = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.id == purchase_item_id)
    )).scalar_one_or_none()
    if not pi:
        raise HTTPException(404, "Позиция закупки не найдена")

    if planned_item_id is not None:
        planned = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id == planned_item_id)
        )).scalar_one_or_none()
        if not planned:
            raise HTTPException(404, "Плановая позиция не найдена")

    pi.feo_planned_item_id = planned_item_id
    await db.commit()
    return {"ok": True, "purchase_item_id": purchase_item_id, "planned_item_id": planned_item_id}


@router.get("/comparison", response_model=FeoComparisonOut)
async def get_comparison(
    feo_category_id: int = Query(...),
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Возвращает плановые позиции и фактические (из закупок) для сравнения."""

    # Плановые позиции
    planned_rows = (await db.execute(
        select(FeoPlannedItem)
        .where(FeoPlannedItem.feo_category_id == feo_category_id)
        .order_by(FeoPlannedItem.id)
    )).scalars().all()

    # Фактические: purchase_items через Purchase.feo_category_id
    stmt = (
        select(PurchaseItem, Purchase)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(Purchase.feo_category_id == feo_category_id)
    )
    if subsidy_id is not None:
        stmt = stmt.where(Purchase.subsidy_id == subsidy_id)

    actual_rows = (await db.execute(stmt)).all()

    # Resolve contractor names
    from app.models.contractor import Contractor
    contractor_ids = {p.contractor_id for _, p in actual_rows if p.contractor_id}
    contractors = {}
    if contractor_ids:
        c_rows = (await db.execute(
            select(Contractor).where(Contractor.id.in_(contractor_ids))
        )).scalars().all()
        contractors = {c.id: c.name for c in c_rows}

    actual_out = []
    for pi, p in actual_rows:
        actual_out.append(FeoActualItemOut(
            purchase_item_id=pi.id,
            item_name=pi.item_name,
            quantity=pi.quantity,
            unit=pi.unit,
            unit_price=pi.unit_price,
            total_price=pi.total_price,
            feo_planned_item_id=pi.feo_planned_item_id,
            purchase_id=p.id,
            purchase_status=p.status,
            contract_number=p.contract_number,
            contractor_name=contractors.get(p.contractor_id) if p.contractor_id else p.item_name,
        ))

    return FeoComparisonOut(
        planned=[FeoPlannedItemOut.model_validate(r) for r in planned_rows],
        actual=actual_out,
    )
