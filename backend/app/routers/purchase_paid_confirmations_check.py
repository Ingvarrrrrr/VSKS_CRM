"""POST /api/subsidies/{subsidy_id}/paid-confirmations/check — выборочная
проверка pending-строк «Оплата найдена в выписке» (см. docstring
purchase_paid_confirmations.py).

Вынесено ОТДЕЛЬНЫМ роутером (ПРАВИЛО №5 — purchase_paid_confirmations.py
уже на границе ~500 строк после перф-доработки 2026-10-06), а не дописано
в тот файл. Доступ/проверки те же (_get_subsidy_or_404 + _assert_can_decide),
а сама симуляция — ТОТ ЖЕ _simulate_confirm_chain, что раньше гонял список
по каждой строке и что до сих пор гоняет одиночный GET по закупке — вторая
копия логики перехода НЕ заводится (ПРАВИЛО №6).

Фронт (PaidConfirmationsPanel.vue / usePaidConfirmations.ts) вызывает этот
эндпоинт порциями по 10 id, последовательно, для строк, которые показаны,
но ещё не провалидированы (checked=false из batch-списка), и мержит
blocked_reason/plan_excess_warning/checked=true в уже загруженные строки —
кнопка «Подтвердить» до этого disabled.
"""
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.purchase import Purchase
from app.models.purchase_paid_confirmation import PurchasePaidConfirmation
from app.routers.purchase_paid_confirmations import (
    _assert_can_decide,
    _get_subsidy_or_404,
    _simulate_confirm_chain,
)

router = APIRouter(tags=["purchase-paid-confirmations"])

_MAX_CHECK_IDS = 20


class _CheckBody(BaseModel):
    ids: list[int]


@router.post("/api/subsidies/{subsidy_id}/paid-confirmations/check")
async def check_subsidy_paid_confirmations(
    subsidy_id: int,
    body: _CheckBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if len(body.ids) > _MAX_CHECK_IDS:
        raise HTTPException(422, f"Максимум {_MAX_CHECK_IDS} запросов за одну проверку")

    await _get_subsidy_or_404(subsidy_id, db)
    await _assert_can_decide(current_user, db, subsidy_id)

    if not body.ids:
        return {"items": []}

    # Чужая субсидия/несуществующий id/уже решённая строка — просто не
    # попадают в выборку и, соответственно, в ответ (владелец: «пропускать»).
    rows = (await db.execute(
        select(PurchasePaidConfirmation).where(
            PurchasePaidConfirmation.id.in_(body.ids),
            PurchasePaidConfirmation.subsidy_id == subsidy_id,
            PurchasePaidConfirmation.status == "pending",
        )
    )).scalars().all()

    items = []
    for c in rows:
        p = await db.get(Purchase, c.purchase_id)
        if p is None:
            continue
        blocked_reason, plan_excess_warning = await _simulate_confirm_chain(db, p, current_user)
        items.append({
            "id": c.id,
            "blocked_reason": blocked_reason,
            "plan_excess_warning": plan_excess_warning,
        })
    return {"items": items}
