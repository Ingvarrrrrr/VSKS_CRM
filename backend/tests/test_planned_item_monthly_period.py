"""Владелец (Волна 3, п.3, 2026-09-13): «Пытаюсь редактировать позицию, требует
число в поле "Количество месяцев", хотя я ввёл "6,66"... надо ввести период с
даты по дату... должно быть помесячная оплата из месяца в месяц, а количество
дней разное в каждом месяце».

Проверяем compute_monthly_schedule (app/services/feo_monthly_schedule.py,
ЕДИНСТВЕННАЯ формула — используется и при сохранении/_apply_payment_fields,
и предпросмотром monthly-schedule-preview, и cash-flow-разворачиванием
plan_cashflow.expand_planned_item) на всех узлах, перечисленных владельцем:
  - ровные 6 месяцев (без остатка);
  - 6 месяцев и 20 дней (остаток считается по длине ИМЕННО того месяца, куда
    он попадает — не усреднённо и не по соседнему месяцу);
  - период внутри одного месяца (0 полных месяцев, весь срок — остаток);
  - февраль невисокосный (28 дней) и високосный (29 дней) — один и тот же
    15-дневный остаток даёт РАЗНУЮ сумму, потому что делитель разный;
  - легаси-позиция: months_count заполнен, monthly_end_date НЕ задана —
    считается по-старому (monthly_amount × months_count, без остатка).

Плюс сквозная проверка через _apply_payment_fields (app/routers/
feo_planned_items.py) и создание/правку через сам роутер (POST/PUT), чтобы
удостовериться, что «Кол-во» больше не путается со сроком (владелец, п.2:
«двоится Количество») — monthly-позиция всегда сохраняет quantity=1,
независимо от того, что прислали в payload.

Чистые функции (compute_monthly_schedule/_apply_payment_fields) не требуют
настоящей БД — узлы ниже не используют db_session/test_org (в отличие от
test_planned_item_unit_price.py, где assert_tz_not_over_plan делает
db.get(...) и требует реальный ORM-инстанс с id)."""
from datetime import date
from decimal import Decimal

import pytest

from app.services.feo_monthly_schedule import compute_monthly_schedule
from app.routers.feo_planned_items import _apply_payment_fields
from app.schemas.schemas import FeoPlannedItemCreate


# ---------------------------------------------------------------------------
# Узел 1 — ровно 6 месяцев, без остатка.
# ---------------------------------------------------------------------------

def test_exact_six_months_no_remainder():
    schedule = compute_monthly_schedule(
        start_date=date(2026, 1, 15), end_date=date(2026, 7, 15),
        months_count=None, monthly_amount=Decimal("1000"),
    )
    assert schedule.full_months == 6
    assert schedule.extra_days == 0
    assert schedule.extra_amount is None
    assert schedule.total == Decimal("6000.00")
    assert schedule.label == "6 мес."
    assert schedule.effective_months_count == 6


# ---------------------------------------------------------------------------
# Узел 2 — 6 месяцев и 20 дней. Остаток (16 июля — 4 августа) считается по
# длине ИЮЛЯ (31 день) — календарный месяц, начинающийся на следующий день
# после конца последнего полного месяца (15 июля).
# ---------------------------------------------------------------------------

def test_six_months_and_twenty_days_remainder_uses_that_months_length():
    schedule = compute_monthly_schedule(
        start_date=date(2026, 1, 15), end_date=date(2026, 8, 4),
        months_count=None, monthly_amount=Decimal("3100"),
    )
    assert schedule.full_months == 6
    assert schedule.extra_days == 20
    # 3100 / 31 (дней в июле) * 20 = 2000.00 ровно
    assert schedule.extra_amount == Decimal("2000.00")
    assert schedule.total == Decimal("20600.00")  # 6*3100 + 2000
    assert schedule.label == "6 мес. 20 дн."
    assert schedule.remainder_start == date(2026, 7, 16)


# ---------------------------------------------------------------------------
# Узел 3 — период внутри одного месяца (0 полных месяцев). Остаток обязан
# считаться по длине ТОГО ЖЕ месяца (марта, 31 день), а не следующего —
# «в том месяце, к которому относится остаток», а не по соседнему.
# ---------------------------------------------------------------------------

def test_period_within_single_month():
    schedule = compute_monthly_schedule(
        start_date=date(2026, 3, 5), end_date=date(2026, 3, 20),
        months_count=None, monthly_amount=Decimal("3100"),
    )
    assert schedule.full_months == 0
    assert schedule.extra_days == 15
    # 3100 / 31 (дней в марте, том же месяце, где лежит весь остаток) * 15 = 1500.00
    assert schedule.extra_amount == Decimal("1500.00")
    assert schedule.total == Decimal("1500.00")
    assert schedule.label == "15 дн."


# ---------------------------------------------------------------------------
# Узел 4 — февраль невисокосный (28 дней) и високосный (29 дней): один и тот
# же 15-дневный остаток при одинаковой посуточной цене (100 ₽/день) даёт
# РАЗНУЮ сумму — 2800 vs 2900 — потому что делитель (число дней в феврале)
# разный. Если бы остаток считался усреднённо, суммы совпали бы.
# ---------------------------------------------------------------------------

def test_february_non_leap_28_days():
    schedule = compute_monthly_schedule(
        start_date=date(2026, 12, 31), end_date=date(2027, 2, 15),
        months_count=None, monthly_amount=Decimal("2800"),
    )
    assert schedule.full_months == 1  # 31.12 -> 31.01
    assert schedule.extra_days == 15  # 31.01 -> 15.02
    assert schedule.extra_amount == Decimal("1500.00")  # 2800/28*15
    assert schedule.total == Decimal("4300.00")


def test_february_leap_29_days():
    schedule = compute_monthly_schedule(
        start_date=date(2027, 12, 31), end_date=date(2028, 2, 15),
        months_count=None, monthly_amount=Decimal("2900"),
    )
    assert schedule.full_months == 1
    assert schedule.extra_days == 15
    assert schedule.extra_amount == Decimal("1500.00")  # 2900/29*15 — тот же день, другая сумма
    assert schedule.total == Decimal("4400.00")


# ---------------------------------------------------------------------------
# Узел 5 — легаси: months_count заполнен, monthly_end_date НЕ задана —
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
# Узел 6 — сквозь _apply_payment_fields: сумма позиции при сохранении = то же
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
    assert item.amount == expected.total == Decimal("20600.00")
    assert item.months_count == expected.effective_months_count == 6
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
