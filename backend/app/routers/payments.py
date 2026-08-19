from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.payment import Payment
from app.schemas.schemas import PaymentCreate, PaymentOut
from app.auth.jwt import get_current_user, require_role, MANAGER_ROLES
from app.auth.permissions import require_tab, require_action
from app.services.purchase_payments import recompute_purchase_payments
from typing import List, Optional

router = APIRouter(prefix="/api/payments", tags=["payments"])

@router.get("/", response_model=List[PaymentOut])
async def list_payments(
    contract_id: Optional[int] = Query(None),
    purchase_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),  # read-only — любой авторизованный (employee видит свои закупки)
):
    q = select(Payment)
    if contract_id:
        q = q.where(Payment.contract_id == contract_id)
    if purchase_id:
        q = q.where(Payment.purchase_id == purchase_id)
    result = await db.execute(q.order_by(Payment.payment_date.desc(), Payment.id.desc()))
    return result.scalars().all()

@router.post("/", response_model=PaymentOut)
async def create_payment(data: PaymentCreate, db: AsyncSession = Depends(get_db), _=Depends(require_action('payment.register'))):
    # Владелец (2026-08-19): «поставленная человеком галочка, что платёж прошёл,
    # без подтверждения выпиской из казначейства, не является подтверждением,
    # что платёж прошёл» — платёж, заведённый вручную через эту форму, остаётся
    # payment_source='manual', confirmed_by_statement=False (заявление, не
    # факт), пока не сопоставится с реальной строкой выписки (см.
    # app/services/payment_lookup.py::attach / purchase_payments.py::create_payments_from_bank,
    # которые тогда ПОМЕЧАЮТ эту же запись подтверждённой, а не заводят вторую).
    # Он попадает в agregat Purchase.payment_amount_declared («заявлено, ждёт
    # подтверждения»), НЕ в Purchase.payment_amount («оплачено») — см.
    # app/services/purchase_payments.py::recompute_purchase_payments.
    #
    # matched_confirmed НЕ ставится в True здесь — по смыслу это «сопоставление
    # строки выписки с закупкой подтверждено», ручной платёж строкой выписки
    # ещё не является.
    #
    # ВАЖНО (порядок commit/recompute верен и оставлен как есть): recompute_purchase_payments
    # сам НЕ коммитит (только flush) — раньше db.commit() стоял ДО него, поэтому
    # пересчитанный Purchase.payment_amount молча терялся при закрытии сессии.
    # Коммитим ОДИН раз, после recompute, чтобы обе записи (Payment +
    # пересчитанный агрегат) попали в одну транзакцию.
    p = Payment(**data.model_dump(), payment_source="manual", confirmed_by_statement=False)
    db.add(p)
    await db.flush()
    if p.purchase_id:
        await recompute_purchase_payments(db, p.purchase_id)
    await db.commit()
    await db.refresh(p)
    return p

@router.delete("/{pid}")
async def delete_payment(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_action('payment.register'))):
    result = await db.execute(select(Payment).where(Payment.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    purchase_id = p.purchase_id
    await db.delete(p)
    # Тот же порядок, что и в create_payment выше: recompute ДО единственного commit.
    if purchase_id:
        await recompute_purchase_payments(db, purchase_id)
    await db.commit()
    return {"ok": True}
