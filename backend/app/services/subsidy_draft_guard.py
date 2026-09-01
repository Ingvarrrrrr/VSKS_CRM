"""Черновые субсидии (план C1/C2, владелец 2026-09-01): «к субсидии не
прикрепляются заявки, договора и прочее, пока её не утвердит администратор».

Единый хелпер для ВСЕХ мест, принимающих subsidy_id при создании/правке
заявки (wishes.py), закупки (purchases.py) или договора (contracts.py) —
чтобы не плодить три копии одной и той же проверки.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy import Subsidy


async def assert_subsidy_approved_for_binding(
    db: AsyncSession, subsidy_id: Optional[int]
) -> None:
    """409, если subsidy_id указывает на ещё не утверждённую (черновую) субсидию.

    subsidy_id is None/0 → привязки нет, проверять нечего.
    Несуществующий subsidy_id тоже пропускаем — 404 по нему выдаст сама
    сущность (заявка/закупка/договор) своей обычной проверкой существования.
    """
    if not subsidy_id:
        return
    status = (await db.execute(
        select(Subsidy.status).where(Subsidy.id == subsidy_id)
    )).scalar_one_or_none()
    if status is not None and status != 'approved':
        raise HTTPException(
            status_code=409,
            detail=(
                "Субсидия ещё не утверждена администратором — привязывать к ней "
                "заявки, закупки или договоры нельзя. Дождитесь утверждения черновика."
            ),
        )
