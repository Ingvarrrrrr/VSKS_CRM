"""plan_funding_sources.py (router) — «Где взять деньги» при превышении плана
(владелец, план .planning/quick/2026-10-05-funding-sources/PLAN.md).

GET  /api/subsidies/{id}/funding-sources — подбор позиций с незаконтрактованным
     остатком, которые можно безболезненно уменьшить, чтобы закрыть превышение
     цели (категории ФЭО или плановой позиции). Доступен любому с правом
     feo_categories (как и остальные read-эндпоинты дерева ФЭО — см.
     app/routers/feo_plan_reads_tree.py).
POST /api/feo-planned-items/{id}/reduce — само уменьшение (+ перенос в целевую
     позицию) — та же матрица доступа, что у PUT /feo-planned-items/{id}
     (require_tab('feo_categories')).

Вся бизнес-логика — app.services.plan_funding_sources (ПРАВИЛО №6: роутер
только достаёт параметры/права и вызывает сервис, второй раз формулы не пишет).
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.feo_planned_item import FeoPlannedItem
from app.services import plan_funding_sources as svc

router = APIRouter(tags=["plan_funding_sources"])


@router.get("/api/subsidies/{subsidy_id}/funding-sources")
async def get_funding_sources(
    subsidy_id: int,
    category_id: Optional[int] = Query(None),
    planned_item_id: Optional[int] = Query(None),
    amount: Optional[float] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """См. контракт API в PLAN.md (целиком в docstring
    app.services.plan_funding_sources). Ровно один из category_id/
    planned_item_id обязателен; amount необязателен — тогда берётся текущее
    превышение цели из дерева ФЭО."""
    return await svc.find_funding_sources(
        db, subsidy_id, category_id=category_id, planned_item_id=planned_item_id, amount=amount,
    )


class ReducePlannedItemRequest(BaseModel):
    amount: Decimal
    target_category_id: Optional[int] = None
    target_planned_item_id: Optional[int] = None
    # Цель — субсидия целиком (GET /funding-sources без category_id/
    # planned_item_id, доп. контракт владельца 05.10.2026) — ОБА target_* выше
    # остаются None (нечего увеличивать), но target_remaining_excess в ответе
    # обязан пересчитаться по бюджету субсидии, не быть null.
    target_subsidy: bool = False
    comment: Optional[str] = None


@router.post("/api/feo-planned-items/{item_id}/reduce")
async def reduce_planned_item(
    item_id: int,
    body: ReducePlannedItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab("feo_categories")),
):
    """Уменьшает плановую позицию `item_id` на `body.amount` (не ниже уже
    законтрактованного — 422 с причиной), опционально переносит сумму в
    `target_planned_item_id` (снимает «ТЗ/договор над плановой позицией») —
    см. app.services.plan_funding_sources.reduce_planned_item_amount за полным
    докстрингом. Права — та же матрица, что у PUT /feo-planned-items/{id}
    (require_tab('feo_categories')): корректировка плана через этот диалог —
    такая же правка справочника ФЭО."""
    item = await db.get(FeoPlannedItem, item_id)
    if item is None:
        raise HTTPException(404, "Плановая позиция не найдена")

    result = await svc.reduce_planned_item_amount(
        db, current_user, item, body.amount,
        target_category_id=body.target_category_id,
        target_planned_item_id=body.target_planned_item_id,
        target_subsidy=body.target_subsidy,
        comment=body.comment,
    )
    await db.commit()
    return result


@router.get("/api/purchases/{purchase_id}/funding-hint")
async def get_purchase_funding_hint(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Для окна отказа 409 «ТЗ/договор над плановой позицией» при оформлении
    закупки — см. app.services.plan_funding_sources.purchase_funding_hint."""
    return await svc.purchase_funding_hint(db, purchase_id)
