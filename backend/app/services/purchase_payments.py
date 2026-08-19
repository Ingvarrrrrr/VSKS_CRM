"""Phase 22 — пересчёт агрегатов Purchase + авто-переход в paid.

Владелец (2026-08-19): «поставленная человеком галочка, что платёж прошёл, без
подтверждения выпиской из казначейства, не является подтверждением, что платёж
прошёл» — payment_amount («оплачено») считается ТОЛЬКО по
Payment.confirmed_by_statement=True; ручные неподтверждённые платежи
(payment_source='manual', confirmed_by_statement=False) идут в отдельный
агрегат payment_amount_declared («заявлено, ждёт подтверждения») и НЕ
участвуют в авто-переходе закупки в статус paid — иначе закупка «закрывалась
бы» по одному лишь слову человека.
"""
from __future__ import annotations
from decimal import Decimal
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.purchase import Purchase


async def find_manual_match(
    db: AsyncSession,
    purchase_id: int,
    document_number: Optional[str],
    payment_date,
    amount,
    tolerance: Decimal = Decimal("0.02"),
) -> Optional[Payment]:
    """Ищет уже существующий РУЧНОЙ неподтверждённый платёж (payment_source='manual',
    confirmed_by_statement=False) на этой закупке с совпадающими номером документа
    (нормализованно), датой и суммой (допуск tolerance).

    Используется при разнесении платежа из казначейской выписки (attach() /
    create_payments_from_bank()) — если находится совпадение, вызывающий код
    должен ПОМЕТИТЬ существующую запись подтверждённой, а не создавать вторую
    (иначе сумма закупки после загрузки выписки удвоится, см. владелец 2026-08-19)."""
    from app.services.payment_basis import normalize_doc_number

    if not purchase_id or amount is None:
        return None

    amount_dec = Decimal(str(amount))
    norm_target = normalize_doc_number(str(document_number or ""))

    candidates = (await db.execute(
        select(Payment).where(
            Payment.purchase_id == purchase_id,
            Payment.payment_source == "manual",
            Payment.confirmed_by_statement == False,  # noqa: E712
        )
    )).scalars().all()

    for c in candidates:
        if c.payment_date != payment_date:
            continue
        if c.amount is None:
            continue
        if abs(Decimal(str(c.amount)) - amount_dec) > tolerance:
            continue
        if normalize_doc_number(str(c.document_number or "")) != norm_target:
            continue
        return c

    return None


async def recompute_purchase_payments(db: AsyncSession, purchase_id: int) -> Purchase:
    """Пересчитать payment_amount (подтверждено казначейством) /
    payment_amount_declared (заявлено, ждёт подтверждения) / doc_number /
    doc_date агрегаты Purchase. Авто-перевод в paid — только если ПОДТВЕРЖДЁННАЯ
    сумма достигла порога."""
    payments = (await db.execute(
        select(Payment).where(Payment.purchase_id == purchase_id)
    )).scalars().all()

    p = await db.get(Purchase, purchase_id)
    if not p:
        return None

    confirmed = [pay for pay in payments if pay.confirmed_by_statement]
    declared = [
        pay for pay in payments
        if pay.payment_source == "manual" and not pay.confirmed_by_statement
    ]

    total_confirmed = sum((Decimal(str(pay.amount)) for pay in confirmed if pay.amount is not None),
                          Decimal(0))
    p.payment_amount = total_confirmed or None

    total_declared = sum((Decimal(str(pay.amount)) for pay in declared if pay.amount is not None),
                         Decimal(0))
    p.payment_amount_declared = total_declared or None

    dates = [pay.payment_date for pay in confirmed if pay.payment_date]
    p.payment_doc_date = max(dates) if dates else None

    numbers = [str(pay.document_number) for pay in confirmed if pay.document_number]
    p.payment_doc_number = "; ".join(numbers) if numbers else None

    # Auto-transition в paid: ТОЛЬКО подтверждённая казначейством сумма достигла
    # порога — ручное «отмечено человеком» само по себе закупку не закрывает.
    threshold = p.contract_price or p.planned_total_price or Decimal(0)
    if total_confirmed > 0 and threshold and total_confirmed >= Decimal(str(threshold)) and p.status == "delivered":
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
        # Владелец (2026-08-19): если на этой закупке уже есть ручной
        # неподтверждённый платёж с тем же номером/датой/суммой — схлопываем
        # выписку В него (подтверждаем), а не заводим вторую запись, иначе
        # сумма закупки после загрузки выписки удвоится.
        existing_manual = await find_manual_match(db, pid, bp.payment_number, bp.payment_date, share)
        if existing_manual is not None:
            existing_manual.bank_payment_id = bp.id
            existing_manual.payment_source = "statement"
            existing_manual.confirmed_by_statement = True
            existing_manual.matched_confirmed = True
            existing_manual.document_number = bp.payment_number
            existing_manual.payment_date = bp.payment_date
            existing_manual.amount = share
            existing_manual.payment_purpose = (bp.purpose_text or "")[:500]
            existing_manual.contract_id = bp.matched_contract_id
            created.append(existing_manual)
            continue

        pay = Payment(
            contract_id=bp.matched_contract_id,
            purchase_id=pid,
            document_number=bp.payment_number,
            payment_purpose=(bp.purpose_text or "")[:500],
            payment_date=bp.payment_date,
            amount=share,
            bank_payment_id=bp.id,
            matched_confirmed=True,
            payment_source="statement",
            confirmed_by_statement=True,
        )
        db.add(pay)
        created.append(pay)

    bp.matched_confirmed = True
    await db.flush()

    # Этап 0 (попутная гигиена): аванс-отчёт из назначения платежа перезаписывает
    # contract_number/date ТОЛЬКО сейчас, в момент реального подтверждения матча —
    # см. app/services/payment_matcher.py::apply_advance_report_override (раньше
    # это было побочным эффектом auto_match на каждом rematch).
    from app.services.payment_matcher import apply_advance_report_override
    for pid in purchase_ids:
        purchase = await db.get(Purchase, pid)
        apply_advance_report_override(purchase, bp)

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
