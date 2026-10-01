"""generate_temp_contract_number — вынесено из app/routers/purchases.py
(рефакторинг 02.10.2026, ПРАВИЛО №5, без изменения поведения).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase


async def generate_temp_contract_number(p: Purchase, db: AsyncSession) -> str:
    """Технический номер договора для рамочной головы, у которой на момент
    формирования документа ещё не известны реальные номер/дата (владелец,
    2026-08-31): «Надо присваивать какой-то технический номер на данный
    момент времени и ставить примечание, что надо актуализировать номер».

    Формат: «ВРЕМ-{№закупки}», если у закупки есть purchase_number, иначе
    «ВРЕМ-{id закупки}». При коллизии с уже занятым contract_number другой
    закупки — добавляется числовой суффикс «-2», «-3», ... до первого
    свободного варианта.
    """
    base_num = p.purchase_number or p.id
    base = f"ВРЕМ-{base_num}"
    candidate = base
    suffix = 1
    while True:
        taken = (await db.execute(
            select(Purchase.id).where(
                Purchase.contract_number == candidate,
                Purchase.id != p.id,
            )
        )).scalar_one_or_none()
        if taken is None:
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"
