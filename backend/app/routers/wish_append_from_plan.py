"""«Добавить забытое из субсидии» — тонкий роутер (Правило №5), парсит запрос
и делегирует в app/services/wish_append_from_plan.py. Та же форма тела, что у
POST /api/feo-planned-items/plan-to-wish/create (ПРАВИЛО №6 — переиспользует
pydantic-схему items оттуда, не копия).

POST /api/wishes/{wish_id}/append-from-plan

Путь на 1 сегмент длиннее catch-all "/{wish_id}" из wishes.router — не
конфликтует с ним независимо от порядка регистрации (тот же принцип, что у
app/routers/wish_items.py: "/{wish_id}/items/{item_id}").

Личность — только из токена (get_current_user), право на правку заявки —
ensure_wish_write_access (тот же гейт, что у PUT /wishes/{id}), субсидия и
остаток плана — build_items_from_plan внутри сервиса. Деньги/цены считаются
только на сервере из плановых позиций — тело присылает только
feo_planned_item_id/quantity/product_id (см. _AppendItem ниже), ничего
денежного от клиента не принимается как истина.
"""
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.services.plan_to_wish import PlanToWishItemInput
from app.services.wish_append_from_plan import append_items_from_plan

router = APIRouter(prefix="/api/wishes", tags=["wishes"])


class _AppendItem(BaseModel):
    feo_planned_item_id: int
    quantity: Decimal = Field(gt=0)
    product_id: Optional[int] = None
    item_name: Optional[str] = None
    unit_price: Optional[Decimal] = None
    price_source: Optional[str] = None  # 'catalog' | 'plan'


class _AppendRequest(BaseModel):
    items: List[_AppendItem]
    # Необязательная подстраховка с фронта (диалог общий с «из плана — в
    # заявку», где subsidy_id обычно уже выбран) — реальная проверка
    # принадлежности субсидии всё равно идёт по wish.subsidy_id внутри
    # сервиса (build_items_from_plan), это поле только для раннего 400, если
    # фронт перепутал диалог.
    subsidy_id: Optional[int] = None


@router.post("/{wish_id}/append-from-plan")
async def post_append_items_from_plan(
    wish_id: int,
    body: _AppendRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if body.subsidy_id is not None:
        from fastapi import HTTPException
        from app.routers.wishes import _load_wish
        wish = await _load_wish(wish_id, db)
        if wish.subsidy_id != body.subsidy_id:
            raise HTTPException(
                400,
                f"Заявка №{wish_id} относится к другой субсидии, а не выбранной ({body.subsidy_id})",
            )

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
    return await append_items_from_plan(db, current_user, wish_id, items)
