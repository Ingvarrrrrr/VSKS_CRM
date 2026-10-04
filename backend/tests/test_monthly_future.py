"""Задача 3 (владелец, 04.10.2026, план .planning/quick/2026-10-04-sheet-ideas):
«остаток помесячных платежей до конца года субсидии»
(app.services.dashboard_monthly_accrual.compute_monthly_future_map).

Контрольный пример: закупка на 12 месяцев (10 000 ₽/мес, договор 120 000 ₽),
начало — 1 января текущего года, без service_end_date (потолок — только
monthly_payment_count=12). Числа считаются ТЕМИ ЖЕ формулами, что и
compute_monthly_ordered_map (_calendar_months/_monthly_schedule_basis,
ПРАВИЛО №6 — не вторая копия), чтобы тест не зависел от даты запуска CI."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.purchase import Purchase
from app.services.dashboard_monthly_accrual import (
    _calendar_months,
    compute_monthly_future_map,
    compute_monthly_ordered_map,
)
from tests.test_feo_plan_tree_scenarios import _make_subsidy


def _identity_filter(q):
    return q


async def _make_monthly_purchase(
    db_session, subsidy_id, start, count_cap, amount_per_month,
    service_end_date=None, status="contracted",
):
    contract_price = amount_per_month * count_cap
    p = Purchase(
        subsidy_id=subsidy_id,
        item_name="Аренда оборудования",
        status=status,
        is_monthly_payment=True,
        monthly_payment_count=count_cap,
        monthly_payment_amount=amount_per_month,
        contract_price=contract_price,
        total_nmck=contract_price,
        nmck=contract_price,
        service_start_date=start,
        service_end_date=service_end_date,
        contract_date=start,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_monthly_future_to_year_end_12_months_contract(db_session, test_org):
    today = date.today()
    subsidy = await _make_subsidy(db_session, test_org.id)
    subsidy.year = today.year
    await db_session.commit()

    start = date(today.year, 1, 1)
    count_cap = 12
    amount_per_month = Decimal("10000")
    await _make_monthly_purchase(db_session, subsidy.id, start, count_cap, amount_per_month)

    # Ожидаемые числа — той же формулой, что и сам модуль (не магические
    # константы, иначе тест ломается в декабре/январе CI).
    months_elapsed = _calendar_months(start, today)
    accrued_months = min(months_elapsed, count_cap)
    expected_accrued = min(amount_per_month * accrued_months, amount_per_month * count_cap)

    year_end = date(today.year, 12, 31)
    total_window_months = min(_calendar_months(start, year_end), count_cap)
    expected_future_months = max(0, total_window_months - accrued_months)
    expected_future = min(
        amount_per_month * expected_future_months,
        max(Decimal(0), amount_per_month * count_cap - expected_accrued),
    )

    ordered_map = await compute_monthly_ordered_map(db_session, _identity_filter)
    future_map = await compute_monthly_future_map(db_session, _identity_filter)

    assert ordered_map.get(subsidy.id, 0.0) == pytest.approx(float(expected_accrued))
    assert future_map.get(subsidy.id, 0.0) == pytest.approx(float(expected_future))
    # Инвариант: начислено + остаток до конца года не превышает полный договор
    # (может быть МЕНЬШЕ — платежи за месяцы СЛЕДУЮЩЕГО года не входят).
    assert ordered_map.get(subsidy.id, 0.0) + future_map.get(subsidy.id, 0.0) <= float(amount_per_month * count_cap) + 0.01


@pytest.mark.asyncio
async def test_monthly_future_capped_by_service_end_date_before_year_end(db_session, test_org):
    """service_end_date раньше 31 декабря — окно обрезается по ней, не по
    концу года (min(service_end_date, год субсидии), как в задаче)."""
    today = date.today()
    subsidy = await _make_subsidy(db_session, test_org.id)
    subsidy.year = today.year
    await db_session.commit()

    start = date(today.year, 1, 1)
    service_end = date(today.year, 3, 31)  # закупка заканчивается в марте
    count_cap = 12
    amount_per_month = Decimal("1000")
    await _make_monthly_purchase(
        db_session, subsidy.id, start, count_cap, amount_per_month, service_end_date=service_end,
    )

    months_elapsed = _calendar_months(start, today)
    accrued_months = min(months_elapsed, count_cap)
    expected_accrued = min(amount_per_month * accrued_months, amount_per_month * count_cap)

    total_window_months = min(_calendar_months(start, service_end), count_cap)
    expected_future_months = max(0, total_window_months - accrued_months)
    expected_future = min(
        amount_per_month * expected_future_months,
        max(Decimal(0), amount_per_month * count_cap - expected_accrued),
    )

    future_map = await compute_monthly_future_map(db_session, _identity_filter)
    assert future_map.get(subsidy.id, 0.0) == pytest.approx(float(expected_future))


@pytest.mark.asyncio
async def test_monthly_future_zero_when_fully_elapsed(db_session, test_org):
    """Договор уже закончился (start 2 года назад, 12 месяцев) — остаток 0,
    не отрицательное число."""
    today = date.today()
    subsidy = await _make_subsidy(db_session, test_org.id)
    subsidy.year = today.year
    await db_session.commit()

    start = date(today.year - 2, 1, 1)
    await _make_monthly_purchase(db_session, subsidy.id, start, 12, Decimal("5000"))

    future_map = await compute_monthly_future_map(db_session, _identity_filter)
    assert future_map.get(subsidy.id, 0.0) == pytest.approx(0.0)
