"""feo_monthly_schedule.py — ЕДИНСТВЕННОЕ место расчёта суммы ежемесячного
платежа плановой позиции ФЭО (FeoPlannedItem, payment_mode='monthly').

ЖАЛОБА ВЛАДЕЛЬЦА (Волна 3, п.3, 2026-09-13): «Пытаюсь редактировать позицию,
требует число в поле "Количество месяцев", хотя я ввёл "6,66"... Наверное,
надо для ежемесячных платежей ввести количество месяцев и дней сверх месяцев
целых... я не знаю, как правильно рассчитывать сумму, т.к. количество дней
разное в каждом месяце, а должно быть помесячная оплата из месяца в месяц».

РЕШЕНИЕ (выбрано владельцем в обсуждении, календарное правило уточнено
🔵 правкой 3 плана abstract-noodling-pelican.md, 15.10.2026): вместо целого
«Количество месяцев» человек вводит ПЕРИОД С ДАТЫ ПО ДАТУ (monthly_start_date/
monthly_end_date). Отчётный период — КАЛЕНДАРНЫЙ месяц до последнего числа;
первый и последний месяц периода (если они неполные) считаются пропорционально
дням ЭТОГО периода в ЭТОМ месяце — см. calendar_month_payments ниже, ОДНА
формула на весь проект (ПРАВИЛО №6), старое правило «месяц от даты до той же
даты» (15.01→15.02) и арифметика «целые месяцы × платёж» удалены.

Пример владельца: период 10.03–27.12, 31 000 ₽/мес → март 22 000 ₽ (22 дня из
31), апрель-ноябрь по 31 000 ₽ (8 полных месяцев), декабрь 27 000 ₽ (27 дней
из 31).

ЕДИНСТВЕННЫЙ ИСТОЧНИК (Правило №6 проекта) — calendar_month_payments
вызывается из:
  - compute_monthly_schedule ниже (плановые позиции ФЭО с periodом);
  - app.routers.feo_planned_items._apply_payment_fields — при сохранении
    (POST/PUT), результат кладётся в FeoPlannedItem.amount/months_count;
  - app.routers.feo_planned_items.monthly_schedule_preview — живая расшифровка
    в диалогах добавления/правки (PlannedItemAddDialog.vue/
    PlannedItemEditDialog.vue), ДО сохранения;
  - app.services.plan_cashflow.expand_planned_item — разворачивание позиции в
    помесячные точки cash-flow графика субсидии;
  - app.services.dashboard_monthly_accrual — график помесячного договора
    (is_monthly_payment=True);
  - app.services.monthly_future_payments — месяц/сумма заказа рамочного
    договора, заданного периодом.
Формула НЕ дублируется ни в одном из этих мест.

ЛЕГАСИ (владелец: «старые позиции с months_count должны продолжать
работать»): если monthly_end_date НЕ задана (позиции, заведённые ДО этой
правки, где months_count вводился вручную как целое число) — период не
считается, работает старая арифметика monthly_amount × months_count, без
остатка дней. Осознанное послабление, как и у unit_price (см. докстринг
FeoPlannedItem.unit_price) — не регресс.
"""
import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

# add_months — уже единственный источник арифметики «прибавить месяцы, но не
# перепрыгнуть через конец месяца» (app.services.plan_cashflow, использовался
# там для разворачивания cash-flow ДО этой задачи). Импортируем, а не дублируем
# (Правило №6). Локальный импорт внутри expand_planned_item (plan_cashflow.py)
# в обратную сторону — модульный импорт здесь безопасен, циклической загрузки
# не возникает (plan_cashflow не импортирует этот модуль на уровне модуля).
from app.services.plan_cashflow import add_months

_MAX_MONTHS_SAFETY = 1200  # 100 лет — защита от зацикливания на «странных» датах

_RU_MONTH_GENITIVE = {
    1: "январь", 2: "февраль", 3: "март", 4: "апрель", 5: "май", 6: "июнь",
    7: "июль", 8: "август", 9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь",
}


def _quantize_money(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class MonthPayment:
    """Один календарный платёж — см. calendar_month_payments ниже."""
    month: date           # 1-е число календарного месяца платежа
    period_from: date     # начало отчётного периода внутри месяца
    period_to: date       # конец отчётного периода внутри месяца (включительно)
    amount: Decimal       # сумма за этот период (пропорция по дням для неполных месяцев)


def calendar_month_payments(start: date, end: date, monthly_amount: Decimal) -> list:
    """ЕДИНСТВЕННАЯ формула календарного помесячного платежа (план владельца
    abstract-noodling-pelican.md, правка 🔵 3, 15.10.2026, п.А): отчётный период
    — календарный месяц до последнего числа; первый и последний (если они
    неполные) считаются пропорционально дням ЭТОГО периода в ЭТОМ месяце:

        платёж = monthly_amount × (дней периода в месяце / дней в месяце)

    округление — ROUND_HALF_UP до копеек. Середина диапазона (не первый и не
    последний месяц) всегда ПОЛНАЯ — платёж = monthly_amount без деления.

    Пример владельца: 10.03–27.12, 31 000 ₽/мес → март 22 000 (22/31 дня),
    апрель-ноябрь по 31 000, декабрь 27 000 (27/31 дня).

    end < start → [] (пустой диапазон — ничего не платится).

    ОДНА точка этого расчёта в проекте (ПРАВИЛО №6) — переиспользуется:
      - compute_monthly_schedule ниже (плановые позиции ФЭО, payment_mode=
        'monthly' с заданным periodом monthly_end_date);
      - app.services.plan_cashflow.expand_planned_item (точки cash-flow);
      - app.services.dashboard_monthly_accrual (график помесячного договора
        is_monthly_payment=True);
      - app.services.monthly_future_payments (месяц заказа рамочного
        договора, заданный периодом service_start_date/service_end_date).
    Арифметика «целые месяцы × платёж» (старое правило «месяц от даты до той
    же даты», например 15.01→15.02) — удалена, второго расчёта нет нигде."""
    if end < start:
        return []
    amt = Decimal(str(monthly_amount))
    result: list = []
    cur = date(start.year, start.month, 1)
    guard = 0
    while cur <= end and guard < _MAX_MONTHS_SAFETY:
        guard += 1
        days_in_month = calendar.monthrange(cur.year, cur.month)[1]
        month_end = date(cur.year, cur.month, days_in_month)
        period_from = max(start, cur)
        period_to = min(end, month_end)
        days_in_period = (period_to - period_from).days + 1
        if days_in_period == days_in_month:
            amount = amt
        else:
            amount = _quantize_money(amt * days_in_period / days_in_month) if days_in_month else Decimal(0)
        result.append(MonthPayment(month=cur, period_from=period_from, period_to=period_to, amount=amount))
        cur = add_months(cur, 1)
    return result


def _calendar_month_weights_sum(start: date, end: date) -> Decimal:
    """Σ «весов» месяцев periodа БЕЗ округления до копеек (1 для полного
    месяца, точная дробь дней/дней_в_месяце для неполного) — вспомогательный
    расчёт ТОЛЬКО для split_amount_by_calendar_period (решение уравнения
    monthly_rate × Σвесов = total_amount); не публикуется как отдельное
    публичное API, т.к. сама по себе не образует платёж."""
    if end < start:
        return Decimal(0)
    total_weight = Decimal(0)
    cur = date(start.year, start.month, 1)
    guard = 0
    while cur <= end and guard < _MAX_MONTHS_SAFETY:
        guard += 1
        days_in_month = calendar.monthrange(cur.year, cur.month)[1]
        month_end = date(cur.year, cur.month, days_in_month)
        period_from = max(start, cur)
        period_to = min(end, month_end)
        days_in_period = (period_to - period_from).days + 1
        total_weight += Decimal(days_in_period) / Decimal(days_in_month) if days_in_period != days_in_month else Decimal(1)
        cur = add_months(cur, 1)
    return total_weight


def split_amount_by_calendar_period(start: date, end: date, total_amount: Decimal) -> list:
    """Разделить ИЗВЕСТНУЮ ИТОГОВУЮ сумму (не ставку в месяц) на помесячные
    платежи ТЕМ ЖЕ календарным правилом, что calendar_month_payments —
    используется app.services.monthly_future_payments для заказа рамочного
    договора, у которого задан период оказания услуги (service_start_date/
    service_end_date), но НЕ задана ставка в месяц, известна только сумма
    заказа целиком (план abstract-noodling-pelican.md, п.B, источник 2).

    Приём (ПРАВИЛО №6 — не вторая формула календаря, только решение
    уравнения поверх первой): «вес» каждого месяца (1 для полного, точная
    дробь дней/дней_в_месяце для неполного, БЕЗ округления до копеек — иначе
    факт округления веса на пробном прогоне ломает финальную ставку, см.
    _calendar_month_weights) даёт Σ весов; эквивалентная месячная ставка =
    total_amount / Σ весов; прогон calendar_month_payments с этой ставкой
    даёт сами платежи (копейки уже округляются ОДИН раз, на итоговых суммах).
    Последний платёж корректируется на копейки округления, чтобы Σ платежей
    == total_amount ТОЧНО (а не ± копейка по сумме независимых округлений)."""
    if end < start or total_amount is None:
        return []
    factor = _calendar_month_weights_sum(start, end)
    if factor == 0:
        return []
    total = Decimal(str(total_amount))
    monthly_rate = total / factor
    payments = calendar_month_payments(start, end, monthly_rate)
    if payments:
        total_q = _quantize_money(total)
        computed = sum((p.amount for p in payments), Decimal(0))
        diff = total_q - computed
        if diff != 0:
            last = payments[-1]
            payments[-1] = MonthPayment(
                month=last.month, period_from=last.period_from, period_to=last.period_to,
                amount=last.amount + diff,
            )
    return payments


@dataclass
class MonthlySchedule:
    # Число ПОЛНЫХ календарных месяцев (без пропорции по дням) в периоде.
    full_months: int
    # Суммарное число дней во ВСЕХ неполных (первом/последнем) месяцах периода.
    extra_days: int
    # Σ сумм неполных месяцев — None, если остатка нет или monthly_amount не задан.
    extra_amount: Optional[Decimal]
    # Построчный календарный разбор (calendar_month_payments) — [] для легаси-
    # режима (months_count без периода) или когда периода недостаточно.
    payments: list = field(default_factory=list)
    # Σ payments[].amount, округлено до копеек. None, если monthly_amount не задан.
    total: Optional[Decimal] = None
    # Человекочитаемая расшифровка, например
    # «март 22 дн. из 31 · 8 полных мес. · декабрь 27 дн. из 31» — для диалогов.
    label: str = "—"
    # Целое число месяцев для обратной совместимости с легаси-потребителями
    # (cash-flow разворачивание, экспорт в xlsx) — при периоде это общее число
    # календарных платежей (len(payments)), при легаси-режиме — months_count.
    effective_months_count: Optional[int] = None


def compute_monthly_schedule(
    start_date: Optional[date],
    end_date: Optional[date],
    months_count: Optional[int],
    monthly_amount: Optional[Decimal],
) -> MonthlySchedule:
    """См. докстринг модуля/calendar_month_payments. Ничего не бросает — на
    нехватку/некорректность данных отвечает «пустой» MonthlySchedule
    (total=None), проверку диапазона дат (end > start) с 400-ответом делает
    вызывающий роутер.

    ИЗМЕНЕНО (🔵 правка 3, 15.10.2026): период считается КАЛЕНДАРНЫМ правилом
    (calendar_month_payments), а не «месяц от даты до той же даты» (15.01→
    15.02). На проде позиций с periodом сейчас 0 — ни одна боевая сумма не
    меняется, меняется только формула для БУДУЩИХ позиций с периодом."""
    amt = Decimal(str(monthly_amount)) if monthly_amount is not None else None

    if start_date is not None and end_date is not None and end_date > start_date:
        calc_amt = amt if amt is not None else Decimal(0)
        payments = calendar_month_payments(start_date, end_date, calc_amt)

        full_count = 0
        extra_days_total = 0
        extra_amount_total = Decimal(0)
        label_parts: list = []
        pending_full = 0

        def _flush_full():
            nonlocal pending_full
            if pending_full:
                label_parts.append(f"{pending_full} полный мес." if pending_full == 1 else f"{pending_full} полных мес.")
                pending_full = 0

        for p in payments:
            days_in_month = calendar.monthrange(p.month.year, p.month.month)[1]
            days_in_period = (p.period_to - p.period_from).days + 1
            if days_in_period == days_in_month:
                full_count += 1
                pending_full += 1
            else:
                _flush_full()
                extra_days_total += days_in_period
                extra_amount_total += p.amount
                label_parts.append(f"{_RU_MONTH_GENITIVE[p.month.month]} {days_in_period} дн. из {days_in_month}")
        _flush_full()

        total: Optional[Decimal] = None
        if amt is not None:
            total = _quantize_money(sum((p.amount for p in payments), Decimal(0)))

        label = " · ".join(label_parts) if label_parts else "0 дн."

        return MonthlySchedule(
            full_months=full_count,
            extra_days=extra_days_total,
            extra_amount=extra_amount_total if (amt is not None and extra_days_total) else None,
            payments=payments,
            total=total,
            label=label,
            effective_months_count=len(payments) or None,
        )

    # Легаси: без периода — старая арифметика monthly_amount × months_count.
    if months_count:
        cnt = int(months_count)
        total = _quantize_money(amt * cnt) if amt is not None else None
        return MonthlySchedule(
            full_months=cnt,
            extra_days=0,
            extra_amount=None,
            payments=[],
            total=total,
            label=f"{cnt} мес.",
            effective_months_count=cnt,
        )

    return MonthlySchedule(
        full_months=0, extra_days=0, extra_amount=None, payments=[],
        total=None, label="—", effective_months_count=None,
    )
