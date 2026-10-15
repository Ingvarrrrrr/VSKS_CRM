"""Ежемесячные закупки: начисление «Заказано» по прошедшим месяцам и остаток
будущих платежей до конца года субсидии.

Извлечено дословно из app/routers/dashboard.py::dashboard_charts при резке
монолита 1641 → core (Правило №5, 2026-09-08) — самодостаточный агрегат,
который читает свои закупки и ничего не решает про фильтр видимости (тот
приходит снаружи через apply_filter, чтобы вызывающая сторона использовала
ТОТ ЖЕ _apply_purchase_org_filter/scope, что и остальная часть /charts —
никакой второй реализации фильтра здесь нет, см. ПРАВИЛО №6).

ИЗМЕНЕНО (🔵 правка 3 плана abstract-noodling-pelican.md, 15.10.2026, п.А):
график помесячного договора (is_monthly_payment=True) считается ОДНОЙ
календарной формулой calendar_month_payments (app.services.feo_monthly_
schedule, ПРАВИЛО №6 — не второй расчёт) вместо старой арифметики «целые
календарные месяцы × ежемесячный платёж» (_calendar_months, удалена).
Период графика — service_start_date/contract_date по service_end_date/
service_deadline_date, либо, если период не задан совсем, до 31.12 года
субсидии. «Начислено» («Заказано») — Σ платежей за месяцы ≤ текущего
(payment.month <= первое число текущего месяца); «будущее» («ещё уйдёт
помесячно до конца года») — Σ платежей за месяцы > текущего и ≤ конца
периода/года субсидии. Потолок Purchase.contract_price (или
planned_total_price) сохранён — ни «начислено», ни «начислено + будущее»
его не превышают.
"""
from datetime import date
from decimal import Decimal
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.services.feo_monthly_schedule import calendar_month_payments


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


_MONTHLY_PURCHASE_COLUMNS = (
    Purchase.id, Purchase.subsidy_id, Purchase.contract_price, Purchase.planned_total_price,
    Purchase.monthly_payment_count, Purchase.monthly_payment_amount,
    Purchase.service_start_date, Purchase.service_end_date,
    Purchase.service_deadline_date, Purchase.contract_date,
)
_MONTHLY_PURCHASE_STATUSES = ["contracted", "ordered", "delivered", "paid"]


class _MonthlyBasis:
    """Общие для «начислено»/«остаток до конца года» величины ОДНОЙ помесячной
    закупки — ОДНА точка разбора графика платежей (ПРАВИЛО №6): и
    compute_monthly_ordered_map, и compute_monthly_future_rows читают
    calendar_month_payments(start, end, amount_per_month) по ЭТОЙ ЖЕ basis,
    не считают график дважды разными формулами."""
    __slots__ = ("start", "end", "amount_per_month", "contract_total", "count_cap")

    def __init__(self, start, end, amount_per_month, contract_total, count_cap):
        self.start = start
        self.end = end
        self.amount_per_month = amount_per_month
        self.contract_total = contract_total
        self.count_cap = count_cap


def _monthly_schedule_basis(r, year_end: date) -> Optional[_MonthlyBasis]:
    """Разбор ОДНОЙ строки _MONTHLY_PURCHASE_COLUMNS (+ year_end субсидии) в
    общие величины графика платежа — start/end/amount_per_month/
    contract_total/count_cap (потолок по количеству месяцев, если
    monthly_payment_count задан). None — расчёт невозможен (нет точки
    отсчёта, период уже закончился раньше, чем начался, либо ни суммы
    платежа, ни способа её вывести)."""
    start = r.service_start_date or r.contract_date
    if not start:
        return None  # нет точки отсчёта — начисление не делаем

    period_end = r.service_end_date or r.service_deadline_date
    end = period_end or year_end
    if end < start:
        return None

    count_cap = int(r.monthly_payment_count) if r.monthly_payment_count else None
    contract_total = r.contract_price if r.contract_price is not None else r.planned_total_price

    amount_per_month = r.monthly_payment_amount
    if amount_per_month is None:
        if contract_total is not None and r.monthly_payment_count:
            amount_per_month = Decimal(contract_total) / Decimal(r.monthly_payment_count)
        else:
            return None  # ни суммы платежа, ни способа её вывести — начисление не делаем

    return _MonthlyBasis(start, end, Decimal(amount_per_month), contract_total, count_cap)


def _basis_payments(basis: _MonthlyBasis) -> list:
    """calendar_month_payments по periodу basis, обрезанный count_cap
    (потолок по количеству месяцев, если он задан) — ОДИН разбор, которым
    пользуются и «начислено», и «будущее»."""
    payments = calendar_month_payments(basis.start, basis.end, basis.amount_per_month)
    if basis.count_cap:
        payments = payments[: basis.count_cap]
    return payments


def _accrued_and_future(basis: _MonthlyBasis, today: date):
    """(accrued, future) Decimal — «начислено» (месяцы ≤ текущего) и «ещё
    уйдёт помесячно» (месяцы > текущего, в пределах periodа/года субсидии),
    с клэмпом по Purchase.contract_price/planned_total_price (итог не
    превышает сумму договора/плана)."""
    payments = _basis_payments(basis)
    cur_month = _month_start(today)
    accrued = sum((p.amount for p in payments if p.month <= cur_month), Decimal(0))
    future = sum((p.amount for p in payments if p.month > cur_month), Decimal(0))
    if basis.contract_total is not None:
        total_cap = Decimal(basis.contract_total)
        accrued = min(accrued, total_cap)
        future = min(future, max(Decimal(0), total_cap - accrued))
    return accrued, future


async def _load_monthly_basis_rows(db: AsyncSession, apply_filter: Callable) -> list:
    """[(row, basis)] — ОДНА точка загрузки is_monthly_payment-закупок с их
    graphic-basis (Subsidy.year нужен для year_end — потолка periodа, если у
    закупки своего service_end_date/service_deadline_date нет). Строки без
    определённой субсидии/года или без достаточных данных графика (basis is
    None) не возвращаются."""
    from app.models.subsidy import Subsidy

    monthly_q = (
        select(*_MONTHLY_PURCHASE_COLUMNS, Subsidy.year.label("subsidy_year"))
        .join(Subsidy, Subsidy.id == Purchase.subsidy_id)
        .where(Purchase.is_monthly_payment == True)
        .where(Purchase.status.in_(_MONTHLY_PURCHASE_STATUSES))
    )
    monthly_q = apply_filter(monthly_q)
    rows = (await db.execute(monthly_q)).all()

    out: list = []
    for r in rows:
        if r.subsidy_id is None or r.subsidy_year is None:
            continue
        year_end = date(r.subsidy_year, 12, 31)
        basis = _monthly_schedule_basis(r, year_end)
        if basis is None:
            continue
        out.append((r, basis))
    return out


async def compute_monthly_ordered_map(
    db: AsyncSession,
    apply_filter: Callable,
    today: Optional[date] = None,
) -> dict:
    """SUM начисленного «Заказано» по ежемесячным закупкам, сгруппировано по
    subsidy_id. is_monthly_payment=true закупки не имеют помесячного графика
    дат — период берём из service_start_date/service_end_date/
    service_deadline_date/contract_date (или до конца года субсидии, если
    период вовсе не задан). Правило пользователя: услуга оказывается по 31
    мая, сегодня 1 июня → июнь уже считается заказанным (обязательство по
    месяцу уже возникло, раз услуга в нём оказывается) — ПОЭТОМУ «начислено»
    = месяцы ≤ ПЕРВОГО числа текущего месяца (см. _accrued_and_future).
    SQL-агрегат total_ordered в dashboard_charts исключает is_monthly_payment
    (Purchase.is_monthly_payment.isnot(True)) — поэтому их вклад в «Заказано»
    приходит РОВНО ОДИН РАЗ, отсюда, начислением. Вызывающая сторона
    СКЛАДЫВАЕТ результат с SQL-агрегатом в итоговое поле total_ordered (не
    оставляет сбоку). Применяется только начиная со статуса «Договор
    заключён» — без договора обязательства нет.

    apply_filter: callable(query) -> query — тот же org/subsidy-видимость
    фильтр (_apply_purchase_org_filter), что и остальная часть /charts,
    применённый вызывающей стороной с нужными current_user/org_ids/
    visible_subsidy_ids.

    `today` — параметр для тестов (по умолчанию date.today())."""
    today = today or date.today()
    rows = await _load_monthly_basis_rows(db, apply_filter)

    monthly_ordered_map: dict = {}
    for r, basis in rows:
        accrued, _future = _accrued_and_future(basis, today)
        if accrued <= 0:
            continue
        monthly_ordered_map[r.subsidy_id] = monthly_ordered_map.get(r.subsidy_id, 0.0) + float(accrued)

    return monthly_ordered_map


async def compute_monthly_future_rows(
    db: AsyncSession,
    apply_filter: Callable,
    today: Optional[date] = None,
) -> list:
    """[{"purchase_id","subsidy_id","amount"}] — ОДНА построчная точка
    разбора «что ещё придётся заплатить по ежемесячным договорам до конца
    года» (source='monthly_contract' для app.services.monthly_future_payments,
    который объединяет эти строки со строками заказов рамочных договоров,
    ПРАВИЛО №6 — второй формулы графика платежей нет, см. докстринг модуля).

    `today` — параметр для тестов (по умолчанию date.today())."""
    today = today or date.today()
    rows = await _load_monthly_basis_rows(db, apply_filter)

    rows_out: list = []
    for r, basis in rows:
        _accrued, future = _accrued_and_future(basis, today)
        if future > 0:
            rows_out.append({
                "purchase_id": r.id, "subsidy_id": r.subsidy_id, "amount": float(future),
            })

    return rows_out


async def compute_monthly_future_map(
    db: AsyncSession,
    apply_filter: Callable,
    today: Optional[date] = None,
) -> dict:
    """SUM будущих помесячных платежей ДО КОНЦА ГОДА субсидии, сгруппировано
    по subsidy_id. ПРАВИЛО №6 — только группирует построчный разбор
    compute_monthly_future_rows выше, сама не считает.

    apply_filter — см. docstring compute_monthly_ordered_map (тот же фильтр
    видимости org/subsidy)."""
    rows = await compute_monthly_future_rows(db, apply_filter, today=today)
    monthly_future_map: dict = {}
    for r in rows:
        monthly_future_map[r["subsidy_id"]] = monthly_future_map.get(r["subsidy_id"], 0.0) + r["amount"]
    return monthly_future_map
