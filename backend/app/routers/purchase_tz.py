"""GET /api/purchases/{id}/tz-rows, PUT /api/purchases/{id}/tz-duplicates.

Под-роутер purchases.py (Правило №5 — не раздувать сам роутер), подключается
`router.include_router(purchase_tz_router)` БЕЗ своего prefix — полный путь
складывается из префикса родителя "/api/purchases" (purchases.router) + пути
здесь. routes.py не трогается — purchases.router уже зарегистрирован.

Решение владельца (21.09, corrections-21-09.md W3): повторяющиеся позиции ТЗ
решает пользователь — merge/keep по каждой группе дублей (см.
app.services.tz_items). Права — как у чтения самой закупки (GET /{pid}), без
дополнительного гейта: правка решений — часть работы с ТЗ, не отдельное
действие с собственным разрешением.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.tz_items import build_tz_rows, serialize_tz_result

router = APIRouter(tags=["purchase-tz"])


class TzDuplicateDecisionsIn(BaseModel):
    decisions: dict[str, str]


async def _load_purchase_with_items(pid: int, db: AsyncSession) -> Purchase:
    result = await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items).selectinload(PurchaseItem.product))
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    return p


@router.get("/{pid}/tz-rows")
async def get_purchase_tz_rows(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    p = await _load_purchase_with_items(pid, db)
    decisions = dict(p.tz_duplicate_decisions or {})
    built = build_tz_rows(p.items or [], decisions)
    return serialize_tz_result(built, decisions)


@router.put("/{pid}/tz-duplicates")
async def put_purchase_tz_duplicates(
    pid: int,
    body: TzDuplicateDecisionsIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    p = await _load_purchase_with_items(pid, db)

    for key, decision in body.decisions.items():
        if decision not in ("merge", "keep"):
            raise HTTPException(422, f"decisions['{key}'] должен быть 'merge' или 'keep', получено: {decision!r}")

    # Merge поверх уже сохранённых решений — пользователь может решать группы
    # по одной, предыдущие решения не должны теряться (тот же приём, что
    # extra_attrs/JSONB-патчи в других роутерах закупки).
    decisions = dict(p.tz_duplicate_decisions or {})
    decisions.update(body.decisions)
    p.tz_duplicate_decisions = decisions
    await db.commit()
    await db.refresh(p, attribute_names=["tz_duplicate_decisions"])

    p = await _load_purchase_with_items(pid, db)
    built = build_tz_rows(p.items or [], decisions)
    return serialize_tz_result(built, decisions)
