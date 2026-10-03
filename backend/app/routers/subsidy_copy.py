"""«Копия субсидии для экспериментов» — POST /api/subsidies/{id}/copy,
DELETE /api/subsidies/{id}/sandbox, POST /api/subsidies/{id}/sandbox/promote
(план breezy-mixing-lovelace.md, Часть Б, 03.10.2026).

Подключён как под-роутер `subsidies.router` (конец app/routers/subsidies.py) —
тот же приём, что уже применяется для fact_import.py в этом проекте.

Право — как у редактирования субсидии (subsidy.edit в орге субсидии), тот же
паттерн, что app.routers.fact_import._check_permission.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.subsidy import Subsidy
from app.auth.jwt import get_current_user
from app.auth.permissions import has_org_key
from app.services.subsidy_copy import (
    create_sandbox_copy, delete_sandbox_copy, dry_run_delete, promote_sandbox_copy,
)

router = APIRouter(tags=["subsidy-copy"])


async def _check_permission(subsidy_id: int, db: AsyncSession, current_user) -> Subsidy:
    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy:
        raise HTTPException(404, "Субсидия не найдена")
    if not await has_org_key(current_user, db, subsidy.org_id, "subsidy.edit", subsidy_id=subsidy_id):
        raise HTTPException(
            403,
            "Копировать/удалять/утверждать эту субсидию может только тот, у кого есть право "
            "её редактирования",
        )
    return subsidy


@router.post("/{subsidy_id}/copy")
async def copy_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Копия субсидии для экспериментов — дерево ФЭО, план, доступы,
    шаблоны, ВСЕ закупки с договорами/позициями/чеками/платежами/файлами.
    Заявки и история согласований не копируются. Может занять время на
    субсидии с сотнями закупок — фронт показывает индикатор загрузки."""
    source = await _check_permission(subsidy_id, db, current_user)
    if source.is_sandbox:
        raise HTTPException(400, "Нельзя копировать копию — скопируйте оригинал")
    new_subsidy = await create_sandbox_copy(db, source)
    await db.commit()
    return {"id": new_subsidy.id, "name": new_subsidy.name, "is_sandbox": True}


@router.delete("/{subsidy_id}/sandbox")
async def delete_sandbox(
    subsidy_id: int,
    dry_run: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Удалить копию целиком. dry_run=true — только посчитать, что уйдёт
    (для диалога подтверждения на фронте), без удаления."""
    subsidy = await _check_permission(subsidy_id, db, current_user)
    if not subsidy.is_sandbox:
        raise HTTPException(400, "Это не копия-песочница — удалить целиком можно только копию")
    if dry_run:
        counts = await dry_run_delete(db, subsidy_id)
        return {"dry_run": True, **counts}
    counts = await delete_sandbox_copy(db, subsidy)
    await db.commit()
    return {"deleted": True, **counts}


@router.post("/{subsidy_id}/sandbox/promote")
async def promote_sandbox(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """«Сделать настоящей» — снимает флаг песочницы. С этого момента числа
    копии учитываются в итогах дашборда/аккаунта как у обычной субсидии;
    если оригинал ещё существует — оба считаются дважды (фронт предупреждает
    об этом перед вызовом)."""
    subsidy = await _check_permission(subsidy_id, db, current_user)
    if not subsidy.is_sandbox:
        raise HTTPException(400, "Это не копия-песочница")
    await promote_sandbox_copy(subsidy)
    await db.commit()
    return {"id": subsidy.id, "is_sandbox": False}
