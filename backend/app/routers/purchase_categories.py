"""Справочник категорий закупки (владелец, 2026-09-16) — CRUD по образцу
других справочников проекта (см. app.routers.expense_codes: публичное
чтение, запись гейтится require_tab). Права на запись — те же, что и на
POST /api/products (require_tab('products') — так же гейтятся соседние
изменяющие ручки products_price.py/products_match.py: /price-actualization,
/deduplicate), чтобы не заводить отдельную роль ради ещё одного справочника
товаров (ПРАВИЛО №6 — не плодить второй набор прав на то же самое).

Отличие от expense_codes (мягкое удаление is_active=False): здесь удаление —
настоящее DELETE, но заблокировано 409, если категория ещё привязана хотя бы
к одному товару (см. product_purchase_categories) — иначе owner не заметит
и потеряет назначения молча.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.purchase_category import PurchaseCategory, product_purchase_categories

router = APIRouter(prefix="/api/purchase-categories", tags=["purchase-categories"])


class PurchaseCategoryOut(BaseModel):
    id: int
    name: str
    sort_order: int
    is_active: bool
    model_config = {"from_attributes": True}


class PurchaseCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1)
    sort_order: int = 0
    is_active: bool = True


class PurchaseCategoryUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("", response_model=List[PurchaseCategoryOut])
async def list_purchase_categories(
    active_only: bool = Query(False, description="Только активные категории"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    stmt = select(PurchaseCategory)
    if active_only:
        stmt = stmt.where(PurchaseCategory.is_active.is_(True))
    stmt = stmt.order_by(PurchaseCategory.sort_order, PurchaseCategory.name)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=PurchaseCategoryOut)
async def create_purchase_category(
    body: PurchaseCategoryCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab("products")),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Название категории не может быть пустым")
    existing = (await db.execute(
        select(PurchaseCategory).where(func.lower(PurchaseCategory.name) == name.lower())
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f'Категория закупки "{name}" уже существует')

    row = PurchaseCategory(name=name, sort_order=body.sort_order, is_active=body.is_active)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/{category_id}", response_model=PurchaseCategoryOut)
async def update_purchase_category(
    category_id: int,
    body: PurchaseCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab("products")),
):
    row = await db.get(PurchaseCategory, category_id)
    if not row:
        raise HTTPException(404, "Категория закупки не найдена")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(422, "Название категории не может быть пустым")
        dup = (await db.execute(
            select(PurchaseCategory).where(
                func.lower(PurchaseCategory.name) == name.lower(),
                PurchaseCategory.id != category_id,
            )
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(409, f'Категория закупки "{name}" уже существует')
        row.name = name
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    if body.is_active is not None:
        row.is_active = body.is_active

    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{category_id}")
async def delete_purchase_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab("products")),
):
    row = await db.get(PurchaseCategory, category_id)
    if not row:
        raise HTTPException(404, "Категория закупки не найдена")

    used_count = (await db.execute(
        select(func.count()).select_from(product_purchase_categories)
        .where(product_purchase_categories.c.purchase_category_id == category_id)
    )).scalar() or 0
    if used_count:
        raise HTTPException(409, {
            "code": "category_in_use",
            "message": f"Категория привязана к {used_count} товар(ам) — сначала снимите привязку",
            "count": used_count,
        })

    await db.delete(row)
    await db.commit()
    return {"ok": True}
