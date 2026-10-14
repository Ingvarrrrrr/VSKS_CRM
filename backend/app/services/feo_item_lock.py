"""Единственное место (ПРАВИЛО №6), решающее — заблокирована ли у позиции
заявки/закупки категория ФЭО, потому что позиция ЗАГРУЖЕНА из Плана закупок.

Решение владельца (14.10.2026, жалобы (а)-(г)): замок раньше стоял на ЛЮБОЙ
позиции с wish_item_id/feo_planned_item_id — но эта связь появляется и у
РУЧНЫХ позиций (auto_assign_planned_items завела свежую авто-плановую строку,
или человек сам выбрал существующую плановую в диалоге «Редактировать
позицию») — их категория должна оставаться редактируемой. Единственный
надёжный признак «из плана» — колонка from_plan (миграция
f1a2b3c4d5e6_purchase_wish_items_from_plan), ставится ТОЛЬКО при рождении
позиции из плана (app/services/plan_to_wish.py::build_items_from_plan) и
переносится при конвертации/пересборке (wish_convert.py, purchases.py).

Используется и PATCH/PUT-гейдами (app/routers/purchase_items_edit.py), и
(через зеркало) фронтом (frontend/src/utils/feoItemLock.ts) — один и тот же
предикат, второй копии не заводим.
"""
from typing import Optional, Protocol

from fastapi import HTTPException


class FeoLockableRow(Protocol):
    from_plan: Optional[bool]


def is_item_feo_locked(item: FeoLockableRow) -> bool:
    """True — категория ФЭО этой позиции (PurchaseItem или WishItem) зафиксирована
    планом и меняется только в плане закупок, до формирования закупки/заявки."""
    return bool(getattr(item, "from_plan", False))


# Единая 409-ка «цена позиции из плана — плановая» (ПРАВИЛО №6): раньше жила
# только инлайном в PATCH /purchases/{id}/items/{item_id}
# (app/routers/purchase_items_edit.py) — PUT /purchases/{id} (полная замена
# позиций) и аналогичные пути заявок молча пропускали смену цены у
# from_plan-позиции. Один текст/код ошибки, один предикат — не копия.
ITEM_PRICE_LOCKED_FROM_PLAN_DETAIL = {
    "code": "ITEM_PRICE_LOCKED_FROM_PLAN",
    "message": "Цена позиции из Плана закупок — плановая, её меняют в плане закупок",
}


def assert_item_price_not_locked(item: FeoLockableRow, new_unit_price) -> None:
    """Бросает HTTPException(409), если у позиции, ЗАГРУЖЕННОЙ из плана
    (is_item_feo_locked), цена в запросе отличается от текущей цены в БД.
    ``new_unit_price`` — значение, присланное клиентом (PATCH body.unit_price
    либо позиция из PUT-пейлоада); сравнение — только когда обе стороны не
    None, иначе сравнение дало бы ложный 409 на позиции без цены вовсе."""
    if not is_item_feo_locked(item):
        return
    current_price = getattr(item, "unit_price", None)
    if new_unit_price is None or current_price is None:
        return
    if new_unit_price != current_price:
        raise HTTPException(409, detail=ITEM_PRICE_LOCKED_FROM_PLAN_DETAIL)
