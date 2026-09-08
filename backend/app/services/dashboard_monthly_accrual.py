"""Ежемесячные закупки: начисление «Заказано» по прошедшим месяцам.

Извлечено дословно из app/routers/dashboard.py::dashboard_charts при резке
монолита 1641 → core (Правило №5, 2026-09-08) — самодостаточный агрегат,
который читает свои закупки и ничего не решает про фильтр видимости (тот
приходит снаружи через apply_filter, чтобы вызывающая сторона использовала
ТОТ ЖЕ _apply_purchase_org_filter/scope, что и остальная часть /charts —
никакой второй реализации фильтра здесь нет, см. ПРАВИЛО №6).
"""
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.services.plan_cashflow import add_months as _add_months


def _calendar_months(start: date, end: date) -> int:
    """Кол-во календарных месяцев от месяца start до месяца end включительно.

    Считает по месяцу/году, день не учитывается (сверено с примером пользователя:
    услуга по 31 мая, сегодня 1 июня → результат уже включает июнь). 0, если end раньше start.
    """
    start_m = date(start.year, start.month, 1)
    end_m = date(end.year, end.month, 1)
    if end_m < start_m:
        return 0
    k = 0
    cur = start_m
    while cur <= end_m:
        k += 1
        cur = _add_months(start_m, k)
    return k


async def compute_monthly_ordered_map(
    db: AsyncSession,
    apply_filter: Callable,
) -> dict:
    """SUM начисленного «Заказано» по ежемесячным закупкам, сгруппировано по subsidy_id.

    is_monthly_payment=true закупки не имеют помесячного графика дат — период берём из
    service_start_date/service_end_date/service_deadline_date/contract_date. Правило
    пользователя: услуга оказывается по 31 мая, сегодня 1 июня → июнь уже считается
    заказанным (обязательство по месяцу уже возникло, раз услуга в нём оказывается).
    SQL-агрегат total_ordered в dashboard_charts исключает is_monthly_payment
    (Purchase.is_monthly_payment.isnot(True)) — поэтому их вклад в «Заказано» приходит
    РОВНО ОДИН РАЗ, отсюда, начислением. Вызывающая сторона СКЛАДЫВАЕТ результат с
    SQL-агрегатом в итоговое поле total_ordered (не оставляет сбоку) — так «Заказано»
    реально включает то, что уже оказывается по ежемесячному договору в этом месяце.
    Применяется только начиная со статуса «Договор заключён» — без договора обязательства нет.

    apply_filter: callable(query) -> query — тот же org/subsidy-видимость фильтр
    (_apply_purchase_org_filter), что и остальная часть /charts, применённый вызывающей
    стороной с нужными current_user/org_ids/visible_subsidy_ids.
    """
    monthly_q = (
        select(
            Purchase.subsidy_id, Purchase.contract_price, Purchase.planned_total_price,
            Purchase.monthly_payment_count, Purchase.monthly_payment_amount,
            Purchase.service_start_date, Purchase.service_end_date,
            Purchase.service_deadline_date, Purchase.contract_date,
        )
        .where(Purchase.is_monthly_payment == True)
        .where(Purchase.status.in_(["contracted", "ordered", "delivered", "paid"]))
    )
    monthly_q = apply_filter(monthly_q)
    monthly_rows = (await db.execute(monthly_q)).all()

    monthly_ordered_map: dict = {}
    _today = date.today()
    for r in monthly_rows:
        start = r.service_start_date or r.contract_date
        if not start:
            continue  # нет точки отсчёта — начисление не делаем

        months_elapsed = _calendar_months(start, _today)
        if months_elapsed <= 0:
            continue

        count_cap = r.monthly_payment_count
        if not count_cap:
            period_end = r.service_end_date or r.service_deadline_date
            derived = _calendar_months(start, period_end) if period_end else 0
            count_cap = derived or None  # None = потолка по месяцам нет

        months_to_pay = min(months_elapsed, count_cap) if count_cap else months_elapsed
        if months_to_pay <= 0:
            continue

        amount_per_month = r.monthly_payment_amount
        if amount_per_month is None:
            contract_total = r.contract_price if r.contract_price is not None else r.planned_total_price
            if contract_total is not None and r.monthly_payment_count:
                amount_per_month = Decimal(contract_total) / Decimal(r.monthly_payment_count)
            else:
                continue  # ни суммы платежа, ни способа её вывести — начисление не делаем

        accrued = Decimal(amount_per_month) * Decimal(months_to_pay)

        contract_total = r.contract_price if r.contract_price is not None else r.planned_total_price
        if contract_total is not None:
            accrued = min(accrued, Decimal(contract_total))  # итог не превышает сумму договора/плана

        if r.subsidy_id is not None:
            monthly_ordered_map[r.subsidy_id] = monthly_ordered_map.get(r.subsidy_id, 0.0) + float(accrued)

    return monthly_ordered_map
