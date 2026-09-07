"""feo_plan_forecast.py — прогноз потолка субсидии («сумма заказанного / потолок»).

Вынесено из feo_plan.py (рефакторинг без изменения поведения, сессия
2026-09-08, см. ПРАВИЛО №5). calculate_ceiling_forecast(s_bulk) читается
через app.routers.subsidies (импортирован туда по имени — monkeypatch в
тестах подменяет subsidies.calculate_ceiling_forecast, а не эту функцию
напрямую, поведение не меняется).
"""
from datetime import date as _date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.services.feo_plan_fact import ORDERED_STATUSES


# ---------------------------------------------------------------------------
# Предупреждение «сумма заказанного приближается к потолку субсидии»
# (владелец, 2026-08-30) — см. Subsidy.ceiling_warn_percent.
# ---------------------------------------------------------------------------
# Статусы «закупка размещена» — те же ORDERED_STATUSES выше ({"ordered",
# "delivered", "paid"}), совпадает с purchase_budget.FACT_STATUSES. Разовые,
# авансовые (purchase_method='advance') и заказы внутри рамочного договора —
# это всё обычные строки Purchase со своим статусом/planned_total_price,
# отдельной обработки не требуют: каждая, дойдя до «Заказано», один раз
# попадает в сумму через этот статусный фильтр. Ежемесячные (is_monthly_payment)
# исключены отсюда явно — у них нет одной прошедшей суммы, есть график
# (см. _monthly_full_schedule_amount ниже), считаются отдельным запросом.
_MONTHLY_ACCRUAL_STATUSES: tuple = ("contracted", "ordered", "delivered", "paid")
"""Начиная с какого статуса ежемесячный платёж уже обязательство (без
подписанного договора обязательства ещё нет) — совпадает с dashboard.py
(app/routers/dashboard.py monthly_q, ~строка 512)."""


def _calendar_months_inclusive(start: Optional[_date], end: Optional[_date]) -> int:
    """Кол-во календарных месяцев от месяца start до месяца end включительно
    (день не учитывается, считаем по году/месяцу). 0, если end раньше start
    или один из аргументов не задан.

    Та же семантика, что и dashboard.py::_calendar_months (~строка 487) —
    пример владельца: услуга оказывается по 31 мая, «сегодня» 1 июня → июнь
    уже входит в результат. Отдельная копия — dashboard.py считает НАКОПЛЕННОЕ
    по прошедшим месяцам от сегодня («Заказано» на текущий момент), а этот
    сервис — ВЕСЬ график целиком независимо от сегодняшней даты (требование
    владельца: «если сейчас апрель, а платежей до декабря — должны посчитаться
    все, а не только по апрель»), поэтому used по-разному ниже.
    """
    if not start or not end:
        return 0
    start_m = _date(start.year, start.month, 1)
    end_m = _date(end.year, end.month, 1)
    if end_m < start_m:
        return 0
    return (end_m.year - start_m.year) * 12 + (end_m.month - start_m.month) + 1


def _monthly_full_schedule_amount(row, today: _date) -> Decimal:
    """Сумма ПОЛНОГО графика одной ежемесячной закупки (весь график целиком,
    не только прошедшие месяцы) — monthly_payment_count × monthly_payment_amount,
    либо контрактная сумма / кол-во платежей, если сумма одного платежа не
    задана явно. Итог не превышает сумму договора/плана (contract_price или
    planned_total_price), если она задана.

    row — строка с полями contract_price, planned_total_price,
    monthly_payment_count, monthly_payment_amount, service_start_date,
    service_end_date, service_deadline_date, contract_date (см. вызывающий код).

    Не задваивается с уже оплаченным: это ОДНА сумма всего графика — сколько
    из неё уже физически оплачено (Purchase.payment_amount), для расчёта
    «сколько ещё заказано» неважно — обязательство по всему графику возникло
    целиком в момент заключения договора, а не по частям по мере оплаты.
    """
    start = row.service_start_date or row.contract_date
    if not start:
        return Decimal("0")  # нет точки отсчёта графика — начисление невозможно (как и в dashboard.py)

    count_cap = row.monthly_payment_count
    if not count_cap:
        period_end = row.service_end_date or row.service_deadline_date
        count_cap = _calendar_months_inclusive(start, period_end) if period_end else None

    if count_cap:
        months_full = count_cap  # весь график известен — берём его целиком, НЕ ограничивая «сегодня»
    else:
        # Ни явного числа платежей, ни определяемого конца периода — «весь график»
        # неизвестен в принципе, единственная доступная оценка — по факту прошедших
        # месяцев (тот же максимум, что доступен dashboard.py «Заказано»).
        months_full = _calendar_months_inclusive(start, today)
    if months_full <= 0:
        return Decimal("0")

    amount_per_month = row.monthly_payment_amount
    contract_total = row.contract_price if row.contract_price is not None else row.planned_total_price
    if amount_per_month is None:
        if contract_total is not None and row.monthly_payment_count:
            amount_per_month = Decimal(str(contract_total)) / Decimal(str(row.monthly_payment_count))
        else:
            return Decimal("0")  # ни суммы платежа, ни способа её вывести

    accrued = Decimal(str(amount_per_month)) * Decimal(str(months_full))
    if contract_total is not None:
        accrued = min(accrued, Decimal(str(contract_total)))
    return accrued


async def _one_off_committed_totals_bulk(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, Decimal]:
    """Σ planned_total_price по закупкам в статусах «Заказано»+ (ORDERED_STATUSES),
    КРОМЕ ежемесячных (те считаются отдельно, весь график — см.
    _monthly_committed_totals_bulk). Покрывает разовые, авансовые
    (purchase_method='advance') и заказы внутри рамочного договора одним
    запросом — это всё обычные строки Purchase, разделения по типу не требуется."""
    if not subsidy_ids:
        return {}
    q = (
        select(Purchase.subsidy_id, func.coalesce(func.sum(Purchase.planned_total_price), 0).label("s"))
        .where(
            Purchase.subsidy_id.in_(subsidy_ids),
            Purchase.status.in_(ORDERED_STATUSES),
            Purchase.is_monthly_payment.isnot(True),
        )
        .group_by(Purchase.subsidy_id)
    )
    rows = (await db.execute(q)).all()
    return {r.subsidy_id: Decimal(str(r.s)) for r in rows}


async def _monthly_committed_totals_bulk(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, Decimal]:
    """Σ ПОЛНОГО графика ежемесячных закупок (is_monthly_payment=True) для набора
    субсидий — см. _monthly_full_schedule_amount. Применяется начиная со статуса
    «Договор» (_MONTHLY_ACCRUAL_STATUSES), как и в dashboard.py."""
    if not subsidy_ids:
        return {}
    q = (
        select(
            Purchase.subsidy_id, Purchase.contract_price, Purchase.planned_total_price,
            Purchase.monthly_payment_count, Purchase.monthly_payment_amount,
            Purchase.service_start_date, Purchase.service_end_date,
            Purchase.service_deadline_date, Purchase.contract_date,
        )
        .where(
            Purchase.subsidy_id.in_(subsidy_ids),
            Purchase.is_monthly_payment.is_(True),
            Purchase.status.in_(_MONTHLY_ACCRUAL_STATUSES),
        )
    )
    rows = (await db.execute(q)).all()
    today = _date.today()
    result: dict[int, Decimal] = {}
    for r in rows:
        accrued = _monthly_full_schedule_amount(r, today)
        if accrued:
            result[r.subsidy_id] = result.get(r.subsidy_id, Decimal("0")) + accrued
    return result


async def calculate_ceiling_forecasts_bulk(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, dict]:
    """Потолок субсидии + «сумма заказанного» + признаки приближения/превышения,
    одним батчем для набора субсидий (см. docstring calculate_ceiling_forecast
    для полной формулы и полей результата). Используется списком субсидий
    (list_subsidies) и дашбордом («субсидии у потолка»).
    """
    if not subsidy_ids:
        return {}
    from app.routers.subsidies import calculate_budgets_bulk  # local: avoid router import cycle

    ceilings = await calculate_budgets_bulk(db, subsidy_ids)
    one_off = await _one_off_committed_totals_bulk(db, subsidy_ids)
    monthly = await _monthly_committed_totals_bulk(db, subsidy_ids)

    subsidies = (await db.execute(
        select(Subsidy.id, Subsidy.ceiling_warn_percent).where(Subsidy.id.in_(subsidy_ids))
    )).all()
    warn_pct_map = {s.id: float(s.ceiling_warn_percent) if s.ceiling_warn_percent is not None else 90.0
                     for s in subsidies}

    result: dict[int, dict] = {}
    for sid in subsidy_ids:
        ceiling = Decimal(str(ceilings.get(sid, 0.0) or 0))
        one_off_total = one_off.get(sid, Decimal("0"))
        monthly_total = monthly.get(sid, Decimal("0"))
        committed_total = one_off_total + monthly_total
        warn_pct = warn_pct_map.get(sid, 90.0)
        pct = float(committed_total / ceiling * 100) if ceiling > 0 else 0.0
        result[sid] = {
            "ceiling_total": float(ceiling),
            "ceiling_committed_total": float(committed_total),
            "ceiling_committed_one_off": float(one_off_total),
            "ceiling_committed_monthly": float(monthly_total),
            "ceiling_committed_percent": round(pct, 1),
            "ceiling_warn_percent": warn_pct,
            "ceiling_near_warning": bool(ceiling > 0 and pct >= warn_pct),
            "ceiling_exceeded": bool(ceiling > 0 and (committed_total - ceiling) > Decimal("0.005")),
        }
    return result


async def calculate_ceiling_forecast(db: AsyncSession, subsidy_id: int) -> dict:
    """Однократный (не-batch) вариант calculate_ceiling_forecasts_bulk — для
    GET /api/subsidies/{id} и после create/update одной субсидии."""
    return (await calculate_ceiling_forecasts_bulk(db, [subsidy_id])).get(subsidy_id, {
        "ceiling_total": 0.0, "ceiling_committed_total": 0.0,
        "ceiling_committed_one_off": 0.0, "ceiling_committed_monthly": 0.0,
        "ceiling_committed_percent": 0.0, "ceiling_warn_percent": 90.0,
        "ceiling_near_warning": False, "ceiling_exceeded": False,
    })



