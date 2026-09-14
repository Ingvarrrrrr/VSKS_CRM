"""feo_monthly_schedule.py — ЕДИНСТВЕННОЕ место расчёта суммы ежемесячного
платежа плановой позиции ФЭО (FeoPlannedItem, payment_mode='monthly').

ЖАЛОБА ВЛАДЕЛЬЦА (Волна 3, п.3, 2026-09-13): «Пытаюсь редактировать позицию,
требует число в поле "Количество месяцев", хотя я ввёл "6,66"... Наверное,
надо для ежемесячных платежей ввести количество месяцев и дней сверх месяцев
целых... я не знаю, как правильно рассчитывать сумму, т.к. количество дней
разное в каждом месяце, а должно быть помесячная оплата из месяца в месяц».

РЕШЕНИЕ (выбрано владельцем в обсуждении): вместо целого «Количество месяцев»
человек вводит ПЕРИОД С ДАТЫ ПО ДАТУ (monthly_start_date/monthly_end_date).
Система сама показывает «6 мес. 20 дн.» и считает:
    сумма = полные_месяцы × ежемесячный_платёж
          + дни_остатка × (ежемесячный_платёж ÷ число_дней_в_том_месяце,
            к которому относится остаток)
Разная длина месяцев учитывается сама собой — остаток считается по длине
КОНКРЕТНОГО календарного месяца, а не усреднённо (30/31/28/29).

«Тот месяц, к которому относится остаток» — календарный месяц, начинающийся
на следующий день после конца последнего ПОЛНОГО месяца периода (см.
_remainder_month_days). Например, период 15.01–04.08 = 6 полных месяцев
(15.01→15.07) + 20 дней остатка (15.07→04.08) — остаток считается по июлю
(31 день), т.к. первый день остатка — 16 июля.

ЕДИНСТВЕННЫЙ ИСТОЧНИК (Правило №6 проекта) — вызывается из:
  - app.routers.feo_planned_items._apply_payment_fields — при сохранении
    (POST/PUT), результат кладётся в FeoPlannedItem.amount/months_count;
  - app.routers.feo_planned_items.monthly_schedule_preview — живая расшифровка
    в диалогах добавления/правки (PlannedItemAddDialog.vue/
    PlannedItemEditDialog.vue), ДО сохранения;
  - app.services.plan_cashflow.expand_planned_item — разворачивание позиции в
    помесячные точки cash-flow графика субсидии.
Формула НЕ дублируется ни в одном из этих трёх мест.

ЛЕГАСИ (владелец: «старые позиции с months_count должны продолжать
работать»): если monthly_end_date НЕ задана (позиции, заведённые ДО этой
правки, где months_count вводился вручную как целое число) — период не
считается, работает старая арифметика monthly_amount × months_count, без
остатка дней. Осознанное послабление, как и у unit_price (см. докстринг
FeoPlannedItem.unit_price) — не регресс.
"""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta
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


@dataclass
class MonthlySchedule:
    full_months: int
    extra_days: int
    # Сумма ТОЛЬКО за остаток дней (без учёта полных месяцев) — None, если
    # остатка нет или monthly_amount не задан.
    extra_amount: Optional[Decimal]
    # Первый календарный день остатка — куда plan_cashflow кладёт точку
    # частичного платежа. None, если остатка нет.
    remainder_start: Optional[date]
    # full_months × monthly_amount + extra_amount, округлено до копеек.
    # None, если monthly_amount не задан (недостаточно данных для суммы).
    total: Optional[Decimal]
    # Человекочитаемая расшифровка, например «6 мес. 20 дн.» — для диалогов.
    label: str
    # Целое число месяцев для обратной совместимости с легаси-потребителями
    # (cash-flow разворачивание, экспорт в xlsx/errors.py PATCHABLE-лейблы) —
    # при периоде это full_months, при легаси-режиме — исходный months_count.
    effective_months_count: Optional[int]


def _quantize_money(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _remainder_month_days(remainder_start: date) -> int:
    return calendar.monthrange(remainder_start.year, remainder_start.month)[1]


def compute_monthly_schedule(
    start_date: Optional[date],
    end_date: Optional[date],
    months_count: Optional[int],
    monthly_amount: Optional[Decimal],
) -> MonthlySchedule:
    """См. докстринг модуля. Ничего не бросает — на нехватку/некорректность
    данных отвечает «пустой» MonthlySchedule (total=None), проверку diapазона
    дат (end > start) с 400-ответом делает вызывающий роутер."""
    amt = Decimal(str(monthly_amount)) if monthly_amount is not None else None

    if start_date is not None and end_date is not None and end_date > start_date:
        full_months = 0
        while full_months < _MAX_MONTHS_SAFETY and add_months(start_date, full_months + 1) <= end_date:
            full_months += 1
        anchor = add_months(start_date, full_months)  # конец последнего полного месяца
        extra_days = (end_date - anchor).days

        extra_amount: Optional[Decimal] = None
        remainder_start: Optional[date] = None
        total: Optional[Decimal] = None
        if extra_days > 0:
            # Первый календарный день остатка — «тот месяц, к которому относится
            # остаток» (формулировка владельца) берём ИМЕННО по этому дню, а не по
            # add_months(anchor, 1): для остатка, целиком лежащего внутри одного
            # месяца (напр. период 05.03–20.03 без полных месяцев), add_months
            # ошибочно прыгнул бы в СЛЕДУЮЩИЙ месяц (апрель) — 15 дней марта
            # считались бы по длине апреля, что не соответствует ни одному
            # разумному прочтению фразы владельца.
            remainder_start = anchor + timedelta(days=1)
            day_count = _remainder_month_days(remainder_start)
            if amt is not None and day_count:
                extra_amount = _quantize_money(amt * extra_days / day_count)
        if amt is not None:
            total = _quantize_money(amt * full_months + (extra_amount or Decimal(0)))

        parts = []
        if full_months:
            parts.append(f"{full_months} мес.")
        if extra_days:
            parts.append(f"{extra_days} дн.")
        label = " ".join(parts) if parts else "0 дн."

        return MonthlySchedule(
            full_months=full_months,
            extra_days=extra_days,
            extra_amount=extra_amount,
            remainder_start=remainder_start,
            total=total,
            label=label,
            effective_months_count=full_months,
        )

    # Легаси: без периода — старая арифметика monthly_amount × months_count.
    if months_count:
        cnt = int(months_count)
        total = _quantize_money(amt * cnt) if amt is not None else None
        return MonthlySchedule(
            full_months=cnt,
            extra_days=0,
            extra_amount=None,
            remainder_start=None,
            total=total,
            label=f"{cnt} мес.",
            effective_months_count=cnt,
        )

    return MonthlySchedule(
        full_months=0, extra_days=0, extra_amount=None, remainder_start=None,
        total=None, label="—", effective_months_count=None,
    )
