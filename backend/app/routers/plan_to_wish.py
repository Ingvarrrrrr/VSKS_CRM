"""«Из плана — в заявку» (plan-to-wish) — тонкий роутер (Правило №5): парсит
запрос, делегирует в app/services/plan_to_wish.py, возвращает результат.
Подключается под-роутером в app/routers/feo_planned_items_matching.py
(`router.include_router(plan_to_wish_router)`) — routes.py уже регистрирует
тот родительский router, отдельного include_router в routes.py не требуется.

Итоговые пути (префикс родителя "/api/feo-planned-items" + "/plan-to-wish" здесь):
  POST /api/feo-planned-items/plan-to-wish/candidates
  POST /api/feo-planned-items/plan-to-wish/create
"""
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.services.plan_to_wish import (
    PlanToWishItemInput,
    build_plan_to_wish_candidates,
    create_wish_from_plan,
)

router = APIRouter(prefix="/plan-to-wish", tags=["feo_planned_items"])


class _CandidatesRequest(BaseModel):
    planned_item_ids: List[int]
    limit: int = 6


@router.post("/candidates")
async def get_plan_to_wish_candidates(
    body: _CandidatesRequest,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    items = await build_plan_to_wish_candidates(db, body.planned_item_ids, body.limit)
    return {"items": items}


class _CreateItem(BaseModel):
    feo_planned_item_id: int
    quantity: Decimal = Field(gt=0)
    product_id: Optional[int] = None
    item_name: Optional[str] = None
    unit_price: Optional[Decimal] = None
    price_source: Optional[str] = None  # 'catalog' | 'plan'


class _CreateRequest(BaseModel):
    subsidy_id: int
    title: Optional[str] = None
    items: List[_CreateItem]


@router.post("/create")
async def post_create_wish_from_plan(
    body: _CreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    items = [
        PlanToWishItemInput(
            feo_planned_item_id=it.feo_planned_item_id,
            quantity=it.quantity,
            product_id=it.product_id,
            item_name=it.item_name,
            unit_price=it.unit_price,
            price_source=it.price_source,
        )
        for it in body.items
    ]
    return await create_wish_from_plan(db, current_user, body.subsidy_id, body.title, items)
