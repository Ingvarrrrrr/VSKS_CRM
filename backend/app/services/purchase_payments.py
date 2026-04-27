"""Phase 22 — пересчёт агрегатов Purchase + авто-переход в paid."""
from __future__ import annotations
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.purchase import Purchase


async def recompute_purchase_payments(db: AsyncSession, purchase_id: int) -> Purchase:
    """Пересчитать payment_amount/doc_number/doc_date агрегаты Purchase
    из всех confirmed Payment-записей. Авто-перевод в paid если порог достигнут."""
    payments = (await db.execute(
        select(Payment).where(
            Payment.purchase_id == purchase_id,
            Payment.matched_confirmed == True,  # noqa: E712
        )
    )).scalars().all()

    p = await db.get(Purchase, purchase_id)
    if not p:
        return None

    total = sum((Decimal(str(pay.amount)) for pay in payments if pay.amount is not None),
                Decimal(0))
    p.payment_amount = total or None

    dates = [pay.payment_date for pay in payments if pay.payment_date]
    p.payment_doc_date = max(dates) if dates else None

    numbers = [str(pay.document_number) for pay in payments if pay.document_number]
    p.payment_doc_number = "; ".join(numbers) if numbers else None

    # Auto-transition в paid: SUM >= порог И есть хотя бы один платёж
    threshold = p.contract_price or p.planned_total_price or Decimal(0)
    if total > 0 and threshold and total >= Decimal(str(threshold)) and p.status == "delivered":
        p.status = "paid"

    await db.flush()
    return p


async def create_payments_from_bank(
    db: AsyncSession,
    bank_payment_id: int,
    purchase_ids: list[int],
) -> list:
    """После того как менеджер подтвердил матч (matched_confirmed=true на BankPayment
    через PATCH /confirm), создать N Payment-записей для указанных закупок.

    Если purchase_ids = [pid_1] → одна запись.
    Если purchase_ids = [pid_1, pid_2, pid_3] → 3 записи с РАВНОЙ долей суммы
    (split по числу закупок). Менеджер может потом скорректировать суммы вручную.
    """
    from app.models.bank_statement import BankPayment
    bp = await db.get(BankPayment, bank_payment_id)
    if not bp:
        raise ValueError(f"BankPayment {bank_payment_id} not found")

    n = len(purchase_ids)
    if n == 0:
        return []

    # Равная доля. Если хочется по-другому — менеджер правит руками после.
    share = (Decimal(str(bp.amount)) / n).quantize(Decimal("0.01")) if bp.amount else Decimal(0)

    created = []
    for pid in purchase_ids:
        pay = Payment(
            contract_id=bp.matched_contract_id,
            purchase_id=pid,
            document_number=bp.payment_number,
            payment_purpose=(bp.purpose_text or "")[:500],
            payment_date=bp.payment_date,
            amount=share,
            bank_payment_id=bp.id,
            matched_confirmed=True,
        )
        db.add(pay)
        created.append(pay)

    bp.matched_confirmed = True
    await db.flush()

    # Recompute aggregates для каждой затронутой закупки
    for pid in purchase_ids:
        await recompute_purchase_payments(db, pid)

    return created


async def unlink_bank_payment(db: AsyncSession, bank_payment_id: int) -> int:
    """Удалить все Payment связанные с этим BankPayment + recompute. Возврат: число удалённых."""
    affected_purchases: set[int] = set()
    payments = (await db.execute(
        select(Payment).where(Payment.bank_payment_id == bank_payment_id)
    )).scalars().all()
    for p in payments:
        if p.purchase_id:
            affected_purchases.add(p.purchase_id)
        await db.delete(p)
    await db.flush()
    for pid in affected_purchases:
        await recompute_purchase_payments(db, pid)
    return len(payments)
