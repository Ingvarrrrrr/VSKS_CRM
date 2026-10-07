# -*- coding: utf-8 -*-
"""Построение заявки-«компаньона» авансового отчёта (Wish source='advance_report').

ОДИН ИСТОЧНИК ИСТИНЫ (ПРАВИЛО №6) для сборки самого компаньона: раньше этот
блок (Wish(...) + копирование позиций в WishItem + hard link purchase_item.
wish_item_id) жил только внутри app/routers/purchases.py::create_purchase —
при заведении задним числом компаньонов для 44 авансовых без заявки (скрипт
backend/scripts/backfill_advance_wishes.py, владелец, 2026-10-07) это
означало бы вторую копию той же сборки. Выносим в эту единственную функцию,
роутер и скрипт зовут её одинаково.

Переиспользует существующие хелперы app/services/advance_wish_sync.py
(wish_item_kwargs_from_purchase_item, sync_wish_contract_and_contractor) —
они уже были единственным источником для «какие поля копируются» и
«контрагент/форма договора по умолчанию»; здесь не продублированы.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.advance_wish_sync import (
    sync_wish_contract_and_contractor,
    wish_item_kwargs_from_purchase_item,
)


def _purchase_item_to_dict(pi: PurchaseItem) -> dict:
    """ORM PurchaseItem → dict с теми же ключами, что PurchaseItemCreate.model_dump()
    отдаёт в роутере (см. purchases.py::create_purchase, ветка is_advance) —
    wish_item_kwargs_from_purchase_item читает ровно эти ключи независимо от
    того, пришли они из pydantic-дампа или из уже сохранённой строки закупки."""
    return dict(
        item_name=pi.item_name,
        item_type=pi.item_type,
        quantity=pi.quantity,
        unit=pi.unit,
        unit_price=pi.unit_price,
        total_price=pi.total_price,
        country_origin=pi.country_origin,
        product_id=pi.product_id,
        feo_category_id=pi.feo_category_id,
        feo_planned_item_id=pi.feo_planned_item_id,
        match_confirmed=bool(pi.match_confirmed),
        over_plan=bool(pi.over_plan),
        extra_attrs=pi.extra_attrs or {},
    )


async def create_advance_companion_wish(
    db: AsyncSession,
    purchase: Purchase,
    purchase_items: Iterable[PurchaseItem],
    *,
    created_by: int,
    org_id: Optional[int],
    status: str = "draft",
    creator=None,
) -> Wish:
    """Создаёт Wish-компаньон авансового отчёта `purchase` + WishItem по каждой
    позиции `purchase_items`, проставляет purchase.wish_id и обратный hard link
    purchase_item.wish_item_id (W1, см. docstring advance_wish_sync.py).

    `purchase_items` — уже существующие ORM PurchaseItem (с id) этой закупки,
    в нужном порядке. `creator` — User-объект автора (для фолбэка ФИО
    контрагента в sync_wish_contract_and_contractor, см. advance_wish_sync.py);
    если не передан — подгружается по `created_by`. Не делает commit — это
    ответственность вызывающего (как и весь остальной код создания закупки/
    заявки в проекте).
    """
    purchase_items = list(purchase_items)

    wish_title = f"Возмещение по авансовому отчёту {purchase.registry_number or f'#{purchase.id}'}"
    estimated_price = purchase.total_nmck if purchase.total_nmck is not None else purchase.contract_price

    wish = Wish(
        source="advance_report",
        status=status,
        title=wish_title[:499],
        created_by=created_by,
        org_id=org_id,
        subsidy_id=purchase.subsidy_id,
        feo_category_id=purchase.feo_category_id,
        event_id=purchase.event_id,
        justification=purchase.service_note_text,
        estimated_price=estimated_price,
    )
    # Форма договора/контрагент компаньона — тот же единственный хелпер, что и
    # при последующей правке авансового в update_purchase (ПРАВИЛО №6).
    if creator is None and created_by is not None:
        from app.models.user import User
        creator = await db.get(User, created_by)
    sync_wish_contract_and_contractor(wish, purchase, creator)
    db.add(wish)
    await db.flush()  # получить wish.id

    purchase.wish_id = wish.id

    new_wish_items: list[WishItem] = []
    for pi in purchase_items:
        wi = WishItem(
            wish_id=wish.id,
            **wish_item_kwargs_from_purchase_item(_purchase_item_to_dict(pi)),
        )
        db.add(wi)
        new_wish_items.append(wi)
    await db.flush()  # получить WishItem.id

    for pi, wi in zip(purchase_items, new_wish_items):
        pi.wish_item_id = wi.id

    return wish
