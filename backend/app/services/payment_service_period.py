"""Месяц оказания услуги для платежей по помесячным закупкам (is_monthly_payment=True —
уборка, связь, предрейсовые осмотры и т.п.): несколько платежей ОДНОЙ суммы приходят
за разные месяцы, и каждый должен лечь на СВОЙ payments.service_period (первое число
месяца), а не все молча на один (уже закрытый) месяц.

Единственное место, где определяется месяц — resolve_service_period() ниже (ПРАВИЛО №6).
Вызывается из ВСЕХ путей создания/подтверждения Payment из выписки:
  - app/services/purchase_payments.py::create_payments_from_bank
  - app/services/payment_lookup.py::attach

При неоднозначности (месяц уже занят / свободных месяцев не осталось) — возвращает
conflict-причину текстом, НЕ бросает исключение сама; вызывающий код решает, что
делать с конфликтом (как payment_lookup уже делает для «два равнозначных кандидата»).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.purchase import Purchase
from app.services.payment_basis import extract_basis
from app.services.plan_cashflow import add_months  # переиспользуем арифметику месяцев, не дублируем (ПРАВИЛО №6)


@dataclass
class ServicePeriodResult:
    period: Optional[_date] = None     # первое число месяца оказания, None если не определён
    conflict: Optional[str] = None     # причина, почему период НЕ определён однозначно
    occupied_period: Optional[_date] = None  # конкретный занятый месяц (если конфликт — именно
    # «месяц уже занят другим платежом»); None для остальных видов конфликта (нет
    # service_start_date / все месяцы периода заняты) — там нет ОДНОГО конкретного месяца


def service_period_conflict_detail(
    message: str,
    purchase_id: Optional[int] = None,
    occupied_period: Optional[_date] = None,
) -> dict:
    """Единственное место, где собирается структурированный detail 409-ответа о
    конфликте месяца оказания (ПРАВИЛО №6) — вызывается из роутеров
    app/routers/bank_statements_registry.py и app/routers/purchase_payment_matching.py
    при перехвате ServicePeriodConflict (purchase_payments.py) / ServicePeriodAttachConflict
    (payment_lookup.py), чтобы фронт (useServicePeriodConflict.ts) мог распознать конфликт
    по полю code, а не парсить текст регуляркой."""
    return {
        "code": "service_period_conflict",
        "purchase_id": purchase_id,
        "message": message,
        "occupied_period": occupied_period.isoformat() if occupied_period else None,
    }


def _month_floor(d: _date) -> _date:
    return d.replace(day=1)


def _fmt_month(d: _date) -> str:
    return d.strftime("%m.%Y")


def _fmt_date(d: Optional[_date]) -> str:
    return d.strftime("%d.%m.%Y") if d else "?"


def _candidate_months(purchase: Purchase) -> list[_date]:
    """Месяцы периода оказания помесячной закупки, по порядку от service_start_date.

    Приоритет длины периода: monthly_payment_count (сколько платежей задумано) >
    service_end_date (конечная дата) > один месяц (если задан только старт)."""
    start = purchase.service_start_date
    if not start:
        return []
    start = _month_floor(start)

    count = purchase.monthly_payment_count
    if count and count > 0:
        return [add_months(start, i) for i in range(count)]

    end = purchase.service_end_date
    if end:
        end = _month_floor(end)
        months = []
        cur = start
        while cur <= end:
            months.append(cur)
            cur = add_months(cur, 1)
        return months

    return [start]


async def _occupied_months(
    db: AsyncSession, purchase_id: int, exclude_payment_id: Optional[int] = None,
) -> dict[_date, Payment]:
    """service_period → Payment, уже занявший этот месяц ПОДТВЕРЖДЁННЫМ платежом
    этой закупки (см. частичный уникальный индекс в миграции p2q4r6s8t0v2)."""
    conditions = [
        Payment.purchase_id == purchase_id,
        Payment.matched_confirmed == True,  # noqa: E712
        Payment.service_period.isnot(None),
    ]
    if exclude_payment_id is not None:
        conditions.append(Payment.id != exclude_payment_id)
    rows = (await db.execute(select(Payment).where(*conditions))).scalars().all()
    return {p.service_period: p for p in rows}


async def resolve_service_period(
    db: AsyncSession,
    purchase: Optional[Purchase],
    payment_like,
    exclude_payment_id: Optional[int] = None,
) -> ServicePeriodResult:
    """Месяц оказания для платежа payment_like (ParsedRow/BankPayment — duck-typed,
    см. payment_basis.py) на закупке purchase.

      - не помесячная закупка (is_monthly_payment != True) → (None, None), поле
        просто не заполняется — это не ошибка;
      - в назначении платежа найден документ-основание с датой (акт/УПД/счёт,
        см. extract_basis) → месяц ЭТОЙ даты; если он уже занят другим
        подтверждённым платежом этой закупки — конфликт;
      - иначе → первый СВОБОДНЫЙ месяц по порядку от service_start_date (в
        пределах monthly_payment_count/service_end_date); если свободных не
        осталось — конфликт.
    """
    if not purchase or not purchase.is_monthly_payment:
        return ServicePeriodResult(None, None)

    occupied = await _occupied_months(db, purchase.id, exclude_payment_id)

    basis = extract_basis(payment_like)
    if basis.date:
        month = _month_floor(basis.date)
        taken = occupied.get(month)
        if taken:
            return ServicePeriodResult(None, (
                f"месяц {_fmt_month(month)} уже оплачен платежом №{taken.document_number or '?'} "
                f"от {_fmt_date(taken.payment_date)}"
            ), occupied_period=month)
        return ServicePeriodResult(month, None)

    months = _candidate_months(purchase)
    if not months:
        return ServicePeriodResult(None, (
            "не задан период оказания услуг (service_start_date) для помесячной "
            "закупки — месяц платежа нужно выбрать вручную"
        ))

    for m in months:
        if m not in occupied:
            return ServicePeriodResult(m, None)

    return ServicePeriodResult(None, "все месяцы периода оказания уже оплачены — нужно выбрать месяц вручную")
