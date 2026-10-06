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
from typing import Callable, Optional

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


_MONTHLY_PURCHASE_COLUMNS = (
    Purchase.id, Purchase.subsidy_id, Purchase.contract_price, Purchase.planned_total_price,
    Purchase.monthly_payment_count, Purchase.monthly_payment_amount,
    Purchase.service_start_date, Purchase.service_end_date,
    Purchase.service_deadline_date, Purchase.contract_date,
)
_MONTHLY_PURCHASE_STATUSES = ["contracted", "ordered", "delivered", "paid"]


class _MonthlyBasis:
    """Общие для «начислено»/«остаток до конца года» величины ОДНОЙ помесячной
    закупки — Задача 3 (владелец, 04.10.2026): compute_monthly_future_map не
    копирует разбор строки compute_monthly_ordered_map, оба читают эту же
    функцию (ПРАВИЛО №6 — одна точка разбора графика платежей)."""
    __slots__ = ("start", "count_cap", "amount_per_month", "contract_total")

    def __init__(self, start, count_cap, amount_per_month, contract_total):
        self.start = start
        self.count_cap = count_cap
        self.amount_per_month = amount_per_month
        self.contract_total = contract_total


def _monthly_schedule_basis(r) -> Optional[_MonthlyBasis]:
    """Разбор ОДНОЙ строки _MONTHLY_PURCHASE_COLUMNS в общие величины графика
    платежа — start/count_cap (потолок по кол-ву месяцев, если задан)/
    amount_per_month/contract_total. None — расчёт невозможен (нет точки
    отсчёта, либо ни суммы платежа, ни способа её вывести)."""
    start = r.service_start_date or r.contract_date
    if not start:
        return None  # нет точки отсчёта — начисление не делаем

    count_cap = r.monthly_payment_count
    if not count_cap:
        period_end = r.service_end_date or r.service_deadline_date
        derived = _calendar_months(start, period_end) if period_end else 0
        count_cap = derived or None  # None = потолка по месяцам нет

    contract_total = r.contract_price if r.contract_price is not None else r.planned_total_price

    amount_per_month = r.monthly_payment_amount
    if amount_per_month is None:
        if contract_total is not None and r.monthly_payment_count:
            amount_per_month = Decimal(contract_total) / Decimal(r.monthly_payment_count)
        else:
            return None  # ни суммы платежа, ни способа её вывести — начисление не делаем

    return _MonthlyBasis(start, count_cap, Decimal(amount_per_month), contract_total)


def _accrued_months_and_amount(basis: _MonthlyBasis, months_elapsed: int) -> tuple:
    """(months_to_pay, accrued) — те самые величины, что считает
    compute_monthly_ordered_map, вынесены сюда, чтобы compute_monthly_future_map
    мог вычесть «уже начислено» из общего окна графика (Задача 3, ПРАВИЛО №6:
    тот же порог/клэмп, не вторая формула)."""
    months_to_pay = min(months_elapsed, basis.count_cap) if basis.count_cap else months_elapsed
    if months_to_pay <= 0:
        return 0, Decimal(0)
    accrued = basis.amount_per_month * Decimal(months_to_pay)
    if basis.contract_total is not None:
        accrued = min(accrued, Decimal(basis.contract_total))  # итог не превышает сумму договора/плана
    return months_to_pay, accrued


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
        select(*_MONTHLY_PURCHASE_COLUMNS)
        .where(Purchase.is_monthly_payment == True)
        .where(Purchase.status.in_(_MONTHLY_PURCHASE_STATUSES))
    )
    monthly_q = apply_filter(monthly_q)
    monthly_rows = (await db.execute(monthly_q)).all()

    monthly_ordered_map: dict = {}
    _today = date.today()
    for r in monthly_rows:
        basis = _monthly_schedule_basis(r)
        if basis is None:
            continue

        months_elapsed = _calendar_months(basis.start, _today)
        if months_elapsed <= 0:
            continue

        _months_to_pay, accrued = _accrued_months_and_amount(basis, months_elapsed)
        if accrued <= 0:
            continue

        if r.subsidy_id is not None:
            monthly_ordered_map[r.subsidy_id] = monthly_ordered_map.get(r.subsidy_id, 0.0) + float(accrued)

    return monthly_ordered_map


async def compute_monthly_future_rows(
    db: AsyncSession,
    apply_filter: Callable,
) -> list:
    """[{"purchase_id","subsidy_id","amount"}] — ОДНА ПОСТРОЧНАЯ точка разбора
    «что ещё придётся заплатить по ежемесячным договорам до конца года»
    (Задача 3, владелец 04.10.2026). Извлечено из compute_monthly_future_map
    (06.10.2026, план sleepy-fluttering-walrus.md п.1 — карточке «Можно
    перераспределить» нужна раскладка этой же суммы по товары/услуги,
    app.services.redistributable_raw.monthly_future_by_kind), ПРАВИЛО №6:
    compute_monthly_future_map ниже теперь только группирует ЭТИ ЖЕ строки по
    subsidy_id — второй формулы графика платежей нет, см. докстринг там же."""
    from app.models.subsidy import Subsidy

    monthly_q = (
        select(*_MONTHLY_PURCHASE_COLUMNS, Subsidy.year.label("subsidy_year"))
        .join(Subsidy, Subsidy.id == Purchase.subsidy_id)
        .where(Purchase.is_monthly_payment == True)
        .where(Purchase.status.in_(_MONTHLY_PURCHASE_STATUSES))
    )
    monthly_q = apply_filter(monthly_q)
    monthly_rows = (await db.execute(monthly_q)).all()

    rows_out: list = []
    _today = date.today()
    for r in monthly_rows:
        basis = _monthly_schedule_basis(r)
        if basis is None:
            continue
        if r.subsidy_id is None or r.subsidy_year is None:
            continue  # нет субсидии/года субсидии — нечем ограничить «до конца года»

        months_elapsed = _calendar_months(basis.start, _today)
        months_to_pay, accrued = _accrued_months_and_amount(basis, max(months_elapsed, 0))

        year_end = date(r.subsidy_year, 12, 31)
        period_end = r.service_end_date or r.service_deadline_date
        window_end = min(period_end, year_end) if period_end else year_end
        total_window_months = _calendar_months(basis.start, window_end)
        if basis.count_cap:
            total_window_months = min(total_window_months, basis.count_cap)

        future_months = max(0, total_window_months - months_to_pay)
        if future_months <= 0:
            continue

        future_amount = basis.amount_per_month * Decimal(future_months)
        if basis.contract_total is not None:
            remaining_cap = max(Decimal(0), Decimal(basis.contract_total) - accrued)
            future_amount = min(future_amount, remaining_cap)

        if future_amount > 0:
            rows_out.append({
                "purchase_id": r.id, "subsidy_id": r.subsidy_id, "amount": float(future_amount),
            })

    return rows_out


async def compute_monthly_future_map(
    db: AsyncSession,
    apply_filter: Callable,
) -> dict:
    """SUM будущих помесячных платежей ДО КОНЦА ГОДА субсидии, сгруппировано
    по subsidy_id — Задача 3 (владелец, 04.10.2026, план .planning/quick/
    2026-10-04-sheet-ideas): «что ещё придётся заплатить по ежемесячным
    договорам в этом году». ПРАВИЛО №6 (06.10.2026) — только группирует
    построчный разбор compute_monthly_future_rows выше, сама не считает.

    apply_filter — см. docstring compute_monthly_ordered_map (тот же фильтр
    видимости org/subsidy).
    """
    rows = await compute_monthly_future_rows(db, apply_filter)
    monthly_future_map: dict = {}
    for r in rows:
        monthly_future_map[r["subsidy_id"]] = monthly_future_map.get(r["subsidy_id"], 0.0) + r["amount"]
    return monthly_future_map
