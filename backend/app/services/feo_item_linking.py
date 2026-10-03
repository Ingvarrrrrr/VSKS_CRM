"""Привязка PurchaseItem к плановой позиции (FeoPlannedItem) — тело
POST /feo-planned-items/map, вынесенное в сервис БЕЗ db.commit() (ПРАВИЛО №6,
план breezy-mixing-lovelace.md, Часть А: «Вынести привязку из POST
/feo-planned-items/map в сервис без commit и использовать и там, и тут»).

Второй потребитель — `historical_fact_import/existing_link.py` (решение
владельца «та же закупка» при импорте факта: непривязанные позиции СУЩЕСТВУЮЩЕЙ
закупки привязываются к строкам плана из файла). Там `enforce_category_check=
False` — предпросмотр УЖЕ показал пользователю пометку «категория: было →
станет» (см. existing_link.py), и решение владельца в предпросмотре заменяет
отказ check_planned_item_category_link; здесь тоже заполняем
item.feo_category_id категорией плановой позиции, а не оставляем прежнюю
(иначе дерево ФЭО не увидит позицию в новой категории, см. commit.py:87-92
соседнего модуля)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish_item import WishItem


async def link_purchase_item_to_planned(
    db: AsyncSession,
    *,
    pi: PurchaseItem,
    planned_item_id: Optional[int],
    current_user,
    enforce_category_check: bool = True,
) -> dict:
    """Сопоставить purchase_item с плановой позицией. planned_item_id=None —
    снять сопоставление. Не коммитит — вызывающая сторона решает, когда.

    Возвращает {ok, purchase_item_id, planned_item_id, moved_to_category_id}
    — та же форма ответа, что был у POST /feo-planned-items/map."""
    if planned_item_id is not None:
        planned = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id == planned_item_id)
        )).scalar_one_or_none()
        if not planned:
            from fastapi import HTTPException
            raise HTTPException(404, "Плановая позиция не найдена")

        purchase = (await db.execute(
            select(Purchase).where(Purchase.id == pi.purchase_id)
        )).scalar_one_or_none()
        effective_cat_id = pi.feo_category_id if pi.feo_category_id is not None else (
            purchase.feo_category_id if purchase else None
        )

        if enforce_category_check:
            from app.services.plan_autoassign import check_planned_item_category_link
            await check_planned_item_category_link(
                db,
                purchase=purchase,
                item=pi,
                item_category_id=effective_cat_id,
                planned_category_id=planned.feo_category_id,
                planned_item_name=planned.name,
                current_user=current_user,
            )
        elif planned.feo_category_id is not None:
            # Решение владельца в предпросмотре уже заменило отказ проверки —
            # категория позиции переносится на категорию плановой позиции
            # явно (иначе дерево ФЭО её не увидит, см. докстринг модуля).
            pi.feo_category_id = planned.feo_category_id
    else:
        planned = None

    pi.feo_planned_item_id = planned_item_id

    # Зеркалим привязку в связанную позицию заявки (см. докстринг исходного
    # POST /feo-planned-items/map — тот же баг с прода, та же причина).
    if pi.wish_item_id is not None:
        wi = (await db.execute(
            select(WishItem).where(WishItem.id == pi.wish_item_id)
        )).scalar_one_or_none()
        if wi:
            wi.feo_planned_item_id = planned_item_id

    return {
        "ok": True,
        "purchase_item_id": pi.id,
        "planned_item_id": planned_item_id,
        "moved_to_category_id": None,
    }
