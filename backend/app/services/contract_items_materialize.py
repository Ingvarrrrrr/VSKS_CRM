"""copy_items_to_contract — материализация ContractItem из PurchaseItem.

Вынесено из app/services/purchase_transition_core.py::apply_purchase_status_
transition, где один и тот же цикл («для каждой PurchaseItem закупки создать
ContractItem, если его ещё нет») был продублирован дважды подряд: в ветке
purchase_method == 'advance' и в ветке elif not tz_required(p) (рефакторинг
02.10.2026, ПРАВИЛО №5/№6, без изменения поведения).

overrides зарезервирован для будущих вызывающих (например, импорта
исторических закупок, где поля ContractItem могут браться не из PurchaseItem
1-в-1) — сегодняшние два вызова его не передают, поведение идентично коду
до выноса.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_item import ContractItem
from app.models.purchase_item import PurchaseItem


async def copy_items_to_contract(
    db: AsyncSession,
    purchase_id: int,
    overrides: Optional[dict] = None,
) -> int:
    """Для каждой PurchaseItem закупки purchase_id без уже существующего
    ContractItem (match по source_item_id) — создаёт ContractItem-копию.
    Не трогает уже существующие ContractItem. Делает db.flush() сам.

    Возвращает итоговое количество ContractItem у этой закупки (после вставки).
    """
    pi_q = await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )
    for pi in pi_q.scalars().all():
        exists_ci = (await db.execute(
            select(ContractItem).where(
                ContractItem.purchase_id == purchase_id,
                ContractItem.source_item_id == pi.id,
            ).limit(1)
        )).scalar_one_or_none()
        if exists_ci:
            continue
        db.add(ContractItem(
            purchase_id=purchase_id,
            source_item_id=pi.id,
            name=pi.item_name or "Позиция",
            quantity=pi.quantity,
            unit=pi.unit or 'шт.',
            unit_price=pi.unit_price,
            total=pi.total_price,
            match_confirmed=True,
        ))
    await db.flush()
    ci_count_res = await db.execute(
        select(func.count()).select_from(ContractItem).where(ContractItem.purchase_id == purchase_id)
    )
    return ci_count_res.scalar() or 0
