"""Гейт категории у позиций заявки, привязанных к плановой позиции плана
закупок (владелец, 2026-09-20, задача 3): «категория позиции берётся из
плановой позиции плана закупок — изменить её можно только в плане, до
формирования закупки». Позиция с feo_planned_item_id расходует конкретную
строку плана (app.services.feo_plan_fact.planned_item_consumption) — если её
feo_category_id разойдётся с категорией самой плановой строки, план
(разбивка по категориям ФЭО) и фактический расход считаются по РАЗНЫМ
категориям, что Правило №6 запрещает.

Единственная точка этой проверки (Правило №6) — используется:
  - app.routers.wish_items.py::patch_wish_item — точечная построчная смена
    категории вне полного пересбора состава заявки;
  - app.routers.wishes.py::update_wish — черновик (delete+recreate): payload
    может прислать НЕСОГЛАСОВАННУЮ пару feo_planned_item_id/feo_category_id
    (например, фронт перетащил позицию в другую категорию, но не сбросил
    старую привязку к плановой позиции) — проверяется по каждой входящей
    позиции при пересборе.

НЕ подключается к app.routers.wish_transitions.py::patch_wish_execution —
там feo_category_id/feo_planned_item_id построчно меняет СОГЛАСУЮЩИЙ через
отдельное право wish.edit_feo, это осознанно разрешённый перенос (с
переездом/отвязкой плановой позиции, см. app.services.plan_autoassign), не
обход этого гейта.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_planned_item import FeoPlannedItem
from app.models.wish_item import WishItem

CATEGORY_FROM_PLAN_MESSAGE = (
    "Категория позиции берётся из плановой позиции плана закупок — изменить "
    "её можно только в плане, до формирования закупки"
)


async def assert_wish_item_category_from_plan(
    db: AsyncSession, item: WishItem, new_feo_category_id: Optional[int],
) -> None:
    """422, если у `item` задан feo_planned_item_id, а `new_feo_category_id`
    отличается от текущей feo_category_id этой плановой позиции.

    `item` может быть как уже персистентным WishItem (PATCH одной позиции),
    так и свежесконструированным, ещё не добавленным в сессию объектом
    (черновичный пересбор в update_wish) — в обоих случаях используется
    только item.feo_planned_item_id, читать/писать сам item здесь не нужно.

    Ничего не проверяет (тихо возвращается), если позиция вообще не
    привязана к плановой позиции, либо привязанная плановая позиция уже не
    существует (её удаление/деактивация — забота другого механизма,
    app.services.plan_autoassign.deactivate_if_orphaned, не этой проверки)."""
    if item.feo_planned_item_id is None:
        return
    planned = await db.get(FeoPlannedItem, item.feo_planned_item_id)
    if planned is None:
        return
    if planned.feo_category_id != new_feo_category_id:
        raise HTTPException(status_code=422, detail=CATEGORY_FROM_PLAN_MESSAGE)
