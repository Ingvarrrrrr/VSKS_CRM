"""Клонирование ВСЕХ PurchaseItem одной закупки в другую закупку — вынесено
из copy_purchases.py (ПРАВИЛО №5/№6, задача 09.10.2026 «восстановление
разбивки позиций ФАДМ 2026_2») в отдельный модуль, чтобы:
  - copy_purchases.py (клон целой закупки при создании копии субсидии/
    дублировании закупок в другую субсидию) и
  - scripts/fadm_restore_items.py (восстановление разбивки позиций УЖЕ
    существующей закупки — без клонирования самой закупки/договора/чека)
использовали ОДНУ функцию клонирования позиции (product_id, item_type, unit,
quantity, unit_price, total_price, формы/form_data, vat и т.д. — ВСЕ колонки
PurchaseItem через clone_row, не ручной список), а не две разные копии
одного и того же цикла.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase_item import PurchaseItem

from ._clone import clone_row


async def clone_purchase_items(
    db: AsyncSession,
    old_purchase_id: int,
    new_purchase_id: int,
    *,
    category_id_map: Optional[dict[int, int]] = None,
    planned_item_id_map: Optional[dict[int, int]] = None,
    receipt_id_map: Optional[dict[int, int]] = None,
    overrides: Optional[dict] = None,
) -> dict[int, int]:
    """Клонирует все PurchaseItem закупки `old_purchase_id` в закупку
    `new_purchase_id` (все колонки — через clone_row, т.е. product_id,
    item_type, unit, quantity, unit_price, total_price, item_form/extra_attrs,
    vat_rate/vat_amount/total_with_vat/vat_on_top и т.д. — копируются как есть).

    category_id_map/planned_item_id_map — перемап FK на НОВОЕ дерево ФЭО (как
    в copy_purchases.py, где это копия ВСЕЙ субсидии); при восстановлении
    разбивки внутри ОДНОЙ субсидии (fadm_restore_items.py) эти карты не нужны
    (FK остаются как у источника, либо передаются `overrides` явным значением
    — см. usage там: все новые позиции привязываются к ОДНОЙ и той же
    feo_planned_item_id/feo_category_id агрегированной позиции, которая была
    на месте клонируемых).

    receipt_id_map — перемап PurchaseItem.receipt_id на клонированные чеки
    (copy_purchases.py); при восстановлении разбивки receipt_id исходных
    позиций обычно отсутствует (чеки привязаны на уровне закупки 89, не её
    позиций) — передавать как есть через overrides, если нужно иное.

    `wish_item_id` всегда сбрасывается в NULL (как в copy_purchases.py) —
    клонированная позиция не является той же строкой заявки.

    Возвращает {старый_item_id: новый_item_id}."""
    category_id_map = category_id_map or {}
    planned_item_id_map = planned_item_id_map or {}
    receipt_id_map = receipt_id_map or {}
    overrides = dict(overrides or {})

    items = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == old_purchase_id)
    )).scalars().all()

    item_id_map: dict[int, int] = {}
    for it in items:
        kwargs = dict(
            purchase_id=new_purchase_id,
            feo_planned_item_id=planned_item_id_map.get(it.feo_planned_item_id) if it.feo_planned_item_id else None,
            feo_category_id=category_id_map.get(it.feo_category_id) if it.feo_category_id else None,
            receipt_id=receipt_id_map.get(it.receipt_id) if it.receipt_id else None,
            wish_item_id=None,
        )
        kwargs.update(overrides)  # overrides побеждают (напр. явный feo_planned_item_id/feo_category_id)
        new_it = clone_row(it, PurchaseItem, **kwargs)
        db.add(new_it)
        await db.flush()
        item_id_map[it.id] = new_it.id
    return item_id_map
