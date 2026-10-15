"""Владелец (Волна 3, п.3, 2026-09-13): «Пытаюсь редактировать позицию, требует
число в поле "Количество месяцев", хотя я ввёл "6,66"... надо ввести период с
даты по дату... должно быть помесячная оплата из месяца в месяц, а количество
дней разное в каждом месяце».

Проверяем compute_monthly_schedule (app/services/feo_monthly_schedule.py,
ЕДИНСТВЕННАЯ формула — используется и при сохранении/_apply_payment_fields,
и предпросмотром monthly-schedule-preview, и cash-flow-разворачиванием
plan_cashflow.expand_planned_item).

ИЗМЕНЕНО (🔵 правка 3 плана abstract-noodling-pelican.md, 15.10.2026, п.А):
период считается КАЛЕНДАРНЫМ правилом (calendar_month_payments) — отчётный
период = календарный месяц до последнего числа, первый/последний неполные
месяцы пропорциональны ДНЯМ ЭТОГО периода В ЭТОМ месяце. Старое правило
«месяц от даты до той же даты» (15.01→15.02) удалено — числа ниже посчитаны
НОВОЙ формулой (см. test_monthly_future_payments.py::test_calendar_month_payments_*
за самим calendar_month_payments, этот файл проверяет обёртку
compute_monthly_schedule/_apply_payment_fields поверх неё)."""
from datetime import date
from decimal import Decimal

import pytest

from app.services.feo_monthly_schedule import compute_monthly_schedule
from app.routers.feo_planned_items import _apply_payment_fields
from app.schemas.schemas import FeoPlannedItemCreate


# ---------------------------------------------------------------------------
# Узел 1 — 15.01–15.07: январь (17 дн. из 31) + 5 полных месяцев + июль (15 дн. из 31).
# ---------------------------------------------------------------------------

def test_calendar_period_with_partial_start_and_end():
    schedule = compute_monthly_schedule(
        start_date=date(2026, 1, 15), end_date=date(2026, 7, 15),
        months_count=None, monthly_amount=Decimal("1000"),
    )
    assert schedule.full_months == 5
    assert schedule.extra_days == 32  # 17 (январь) + 15 (июль)
    assert schedule.total == Decimal("6032.26")  # 1000*17/31 + 5*1000 + 1000*15/31
    assert schedule.label == "январь 17 дн. из 31 · 5 полных мес. · июль 15 дн. из 31"
    assert schedule.effective_months_count == 7  # число календарных платежей, не только полных


# ---------------------------------------------------------------------------
# Узел 2 — 15.01–04.08: январь (17 дн. из 31) + 6 полных месяцев + август (4 дн. из 31).
# ---------------------------------------------------------------------------

def test_period_with_partial_start_and_short_end():
    schedule = compute_monthly_schedule(
        start_date=date(2026, 1, 15), end_date=date(2026, 8, 4),
        months_count=None, monthly_amount=Decimal("3100"),
    )
    assert schedule.full_months == 6
    assert schedule.extra_days == 21  # 17 (январь) + 4 (август)
    assert schedule.extra_amount == Decimal("2100.00")  # 3100/31*17 + 3100/31*4 = 1700+400
    assert schedule.total == Decimal("20700.00")  # 1700 + 6*3100 + 400
    assert schedule.label == "январь 17 дн. из 31 · 6 полных мес. · август 4 дн. из 31"
    assert schedule.effective_months_count == 8


# ---------------------------------------------------------------------------
# Узел 3 — период внутри одного месяца (0 полных месяцев). Остаток считается
# по длине ТОГО ЖЕ месяца (марта, 31 день) — «в том месяце, к которому
# относится остаток», а не по соседнему.
# ---------------------------------------------------------------------------

def test_period_within_single_month():
    schedule = compute_monthly_schedule(
        start_date=date(2026, 3, 5), end_date=date(2026, 3, 20),
        months_count=None, monthly_amount=Decimal("3100"),
    )
    assert schedule.full_months == 0
    assert schedule.extra_days == 16  # 05.03..20.03 включительно
    # 3100 / 31 (дней в марте) * 16 = 1600.00
    assert schedule.extra_amount == Decimal("1600.00")
    assert schedule.total == Decimal("1600.00")
    assert schedule.label == "март 16 дн. из 31"
    assert schedule.effective_months_count == 1


# ---------------------------------------------------------------------------
# Узел 4/5 — период декабрь→февраль, захватывающий невисокосный и високосный
# февраль: день остатка в декабре (1 дн. из 31) одинаков, но дневная ставка в
# феврале (15 дн.) разная — 2800/28=100 ₽/день vs 2900/29=100 ₽/день — РАЗНЫЕ
# monthly_amount подобраны так, чтобы дневная ставка в феврале совпала (100
# ₽/день), демонстрируя, что делитель — именно число дней ИМЕННО этого месяца.
# ---------------------------------------------------------------------------

def test_period_spanning_non_leap_february():
    schedule = compute_monthly_schedule(
        start_date=date(2026, 12, 31), end_date=date(2027, 2, 15),
        months_count=None, monthly_amount=Decimal("2800"),
    )
    assert schedule.full_months == 1  # январь целиком
    assert schedule.extra_days == 16  # 1 (31.12) + 15 (01.02-15.02)
    # декабрь: 2800/31*1 = 90.32; февраль (28 дн.): 2800/28*15 = 1500.00
    assert schedule.extra_amount == Decimal("1590.32")
    assert schedule.total == Decimal("4390.32")  # 90.32 + 2800 + 1500.00
    assert schedule.label == "декабрь 1 дн. из 31 · 1 полный мес. · февраль 15 дн. из 28"


def test_period_spanning_leap_february():
    schedule = compute_monthly_schedule(
        start_date=date(2027, 12, 31), end_date=date(2028, 2, 15),
        months_count=None, monthly_amount=Decimal("2900"),
    )
    assert schedule.full_months == 1
    assert schedule.extra_days == 16
    # декабрь: 2900/31*1 = 93.55; февраль (29 дн., високосный): 2900/29*15 = 1500.00
    assert schedule.extra_amount == Decimal("1593.55")
    assert schedule.total == Decimal("4493.55")  # 93.55 + 2900 + 1500.00 — отличается от non-leap теста
    assert schedule.label == "декабрь 1 дн. из 31 · 1 полный мес. · февраль 15 дн. из 29"


# ---------------------------------------------------------------------------
# Узел 6 — легаси: months_count заполнен, monthly_end_date НЕ задана —
# продолжает считаться по старой формуле (monthly_amount × months_count),
# без остатка дней. «Не сломай старые позиции».
# ---------------------------------------------------------------------------

def test_legacy_months_count_without_end_date_unchanged():
    schedule = compute_monthly_schedule(
        start_date=date(2026, 1, 15), end_date=None,
        months_count=6, monthly_amount=Decimal("1000"),
    )
    assert schedule.full_months == 6
    assert schedule.extra_days == 0
    assert schedule.total == Decimal("6000.00")
    assert schedule.effective_months_count == 6
    assert schedule.label == "6 мес."


def test_legacy_months_count_fractional_input_rejected_by_schema():
    """До этой правки «6,66» уходило прямо в Integer-колонку months_count и
    валилось на уровне БД/схемы — убеждаемся, что схема по-прежнему требует
    целое (см. FeoPlannedItemCreate.months_count: Optional[int]), т.е. дробное
    значение теперь просто некуда ввести (UI больше не показывает это поле,
    см. PlannedItemAddDialog.vue/PlannedItemEditDialog.vue)."""
    with pytest.raises(Exception):
        FeoPlannedItemCreate(feo_category_id=1, name="x", payment_mode="monthly", months_count=6.66)


# ---------------------------------------------------------------------------
# Узел 7 — сквозь _apply_payment_fields: сумма позиции при сохранении = то же
# число, что вернула бы compute_monthly_schedule напрямую (единственная
# формула, Правило №6), и «Кол-во» принудительно 1 для monthly (владелец,
# п.2 «двоится Количество») — даже если в payload прислали другое quantity.
# ---------------------------------------------------------------------------

class _FakeItem:
    """Минимальная заглушка ORM-объекта — _apply_payment_fields читает/пишет
    только простые атрибуты, полноценная FeoPlannedItem (с обязательным
    feo_category_id/name на уровне БД) здесь не нужна."""
    payment_mode = None
    planned_date = None
    monthly_start_date = None
    monthly_end_date = None
    monthly_amount = None
    months_count = None
    amount = None
    quantity = None


def test_apply_payment_fields_uses_single_formula_and_forces_quantity_one():
    item = _FakeItem()
    data = FeoPlannedItemCreate(
        feo_category_id=1, name="Аренда офиса",
        quantity=Decimal("6.66"),  # владелец когда-то ввёл сюда дробное число месяцев
        payment_mode="monthly",
        monthly_start_date=date(2026, 1, 15),
        monthly_end_date=date(2026, 8, 4),
        monthly_amount=Decimal("3100"),
    )
    _apply_payment_fields(item, data)

    expected = compute_monthly_schedule(
        start_date=date(2026, 1, 15), end_date=date(2026, 8, 4),
        months_count=None, monthly_amount=Decimal("3100"),
    )
    assert item.amount == expected.total == Decimal("20700.00")
    assert item.months_count == expected.effective_months_count == 8
    # Владелец, Волна 3, п.2: «Кол-во» ≠ месяцы — 6.66 из payload НЕ попадает
    # в quantity, monthly-позиция всегда фиксирует 1.
    assert item.quantity == Decimal("1")


def test_apply_payment_fields_legacy_item_without_end_date_keeps_old_amount():
    """Старая позиция: months_count=6 вручную, monthly_end_date не прислана —
    сумма считается по легаси-формуле (monthly_amount × months_count), не
    ломается переходом на период."""
    item = _FakeItem()
    data = FeoPlannedItemCreate(
        feo_category_id=1, name="Логистические услуги",
        payment_mode="monthly",
        monthly_start_date=date(2026, 1, 15),
        monthly_end_date=None,
        months_count=6,
        monthly_amount=Decimal("1000"),
    )
    _apply_payment_fields(item, data)
    assert item.amount == Decimal("6000.00")
    assert item.months_count == 6
    assert item.quantity == Decimal("1")


def test_apply_payment_fields_one_time_keeps_manual_quantity():
    """Разовый режим — quantity/amount как прислали, без вмешательства
    ежемесячной нормализации (это правило только для payment_mode='monthly')."""
    item = _FakeItem()
    data = FeoPlannedItemCreate(
        feo_category_id=1, name="Оборудование",
        payment_mode="one_time",
        quantity=Decimal("5"),
        amount=Decimal("50000"),
    )
    _apply_payment_fields(item, data)
    assert item.quantity == Decimal("5")
    assert item.amount == Decimal("50000")
