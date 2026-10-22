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
  - app.routers.wishes.py::update_wish — ЦЕЛИКОМ, оба пути:
      * черновик (delete+recreate): payload может прислать НЕСОГЛАСОВАННУЮ
        пару feo_planned_item_id/feo_category_id (например, фронт перетащил
        позицию в другую категорию, но не сбросил старую привязку к плановой
        позиции) — проверяется по каждой входящей позиции при пересборе;
      * non-draft PUT (update in-place по id): раньше смена feo_category_id
        позиции без переприсылки feo_planned_item_id молча переносила/
        отвязывала плановую позицию (см. app.services.plan_autoassign.
        move_or_detach_planned_item). Владелец (22.10.2026, заявка №209)
        отменил это разрешение — тот же 422, не вторая копия правила;
  - app.routers.wish_transitions.py::patch_wish_execution — построчные
    ФЭО-правки согласующего (WishItemFeoPatch): та же отмена молчаливого
    переноса/отвязки (владелец, 22.10.2026, заявка №209) — «категория
    позиции по плану не меняется» действует и для согласующего. MSG_HEADER_LOCKED
    ниже — текст отказа при попытке сменить категорию ШАПКИ заявки, у которой
    ВСЕ позиции по плану (смешанные заявки шапку менять не блокируют).
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

# Владелец (22.10.2026, заявка №209): если у заявки ВСЕ позиции — по плану
# (feo_planned_item_id задан у каждой), категорию ШАПКИ менять нельзя вовсе —
# позиции за ней не последуют (sync_items_to_header_category их пропускает),
# смена шапки была бы бессмысленной. Смешанные заявки — шапку менять можно,
# позиции по плану просто останутся в своей категории.
MSG_HEADER_LOCKED = (
    "Категория ФЭО позиций задана планом закупок — у позиций по плану её менять нельзя. "
    "Категорию можно выбрать только у позиций, добавленных вручную, — в строке позиции."
)


def wish_items_all_plan_linked(items) -> bool:
    """True — у заявки есть позиции И ВСЕ они по плану (feo_planned_item_id
    задан у каждой). Пустой список позиций — False (нет позиций, нечего
    блокировать). См. MSG_HEADER_LOCKED выше."""
    items = list(items)
    if not items:
        return False
    return all(getattr(it, "feo_planned_item_id", None) is not None for it in items)


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
