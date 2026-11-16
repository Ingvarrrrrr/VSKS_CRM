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


def _get_loaded_planned_item(item):
    """Возвращает уже загруженный item.planned_item без ленивого запроса в БД
    (защита от MissingGreenlet в синхронных хелперах/тестах)."""
    try:
        from sqlalchemy import inspect as sa_inspect
        state = sa_inspect(item)
        if "planned_item" in state.unloaded:
            return None
    except Exception:
        pass
    return getattr(item, "planned_item", None)


def is_wish_item_plan_locked(item) -> bool:
    """True — позиция заявки привязана к предсуществующей позиции Плана закупок
    (загружена из плана `from_plan=True` ИЛИ привязана к не-автосозданной
    `FeoPlannedItem` с `auto_created=False`). Если `FeoPlannedItem` была создана
    автоматически при согласовании самой заявки (`auto_created=True` и `from_plan=False`),
    категория позиции НЕ заблокирована планом."""
    if getattr(item, "from_plan", False):
        return True
    if getattr(item, "feo_planned_item_id", None) is None:
        return False
    planned = _get_loaded_planned_item(item)
    if planned is not None and getattr(planned, "auto_created", False):
        return False
    if getattr(item, "planned_item_auto_created", False):
        return False
    return True


def wish_items_all_plan_linked(items, *, is_advance_report: bool = False) -> bool:
    """True — у заявки есть позиции И ВСЕ они заблокированы предсуществующим
    планом закупок (`is_wish_item_plan_locked`). Пустой список позиций — False.
    Для авансовых отчётов (is_advance_report=True) всегда False."""
    if is_advance_report:
        return False
    items = list(items)
    if not items:
        return False
    return all(is_wish_item_plan_locked(it) for it in items)


async def assert_wish_item_category_from_plan(
    db: AsyncSession, item: WishItem, new_feo_category_id: Optional[int], *, is_advance_report: bool = False,
) -> None:
    """422, если у `item` задан feo_planned_item_id, привязанный к предсуществующему
    плану закупок (не auto_created или при from_plan=True), а `new_feo_category_id`
    отличается от текущей feo_category_id этой плановой позиции."""
    if is_advance_report or item.feo_planned_item_id is None:
        return
    planned = await db.get(FeoPlannedItem, item.feo_planned_item_id)
    if planned is None:
        return
    if planned.auto_created and not getattr(item, "from_plan", False):
        return
    if planned.feo_category_id != new_feo_category_id:
        raise HTTPException(status_code=422, detail=CATEGORY_FROM_PLAN_MESSAGE)
