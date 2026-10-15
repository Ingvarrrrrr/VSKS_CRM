"""test_monthly_future_payments.py — план владельца abstract-noodling-
pelican.md, п.A/B/C (15.10.2026): календарь платежей с пропорцией по дням,
месяц заказа рамочного договора (по полю/по порядку номеров), «ещё уйдёт
помесячно до конца года», и инвариант четырёх строк карточки «Можно
перераспределить».

ПРАВИЛО №6 — ни один тест не изобретает вторую формулу: ожидаемые числа либо
посчитаны вручную по формуле из плана (calendar_month_payments), либо сверены
между двумя независимыми способами чтения ОДНОГО И ТОГО ЖЕ правила
(committed_consumption_by_category / not_committed_raw_by_subsidy)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.feo_monthly_schedule import calendar_month_payments
from app.services.monthly_future_payments import (
    framework_order_month_rows,
    monthly_future_rows,
    monthly_future_totals_by_subsidy,
    monthly_future_not_started_by_subsidy,
)
from app.services.redistributable_raw import not_committed_raw_by_subsidy
from app.services.subsidy_money_summary import subsidy_money_summary
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


# ---------------------------------------------------------------------------
# calendar_month_payments — формула владельца (план, правка 🔵3, п.3).
# ---------------------------------------------------------------------------

def test_calendar_month_payments_owner_example():
    payments = calendar_month_payments(date(2026, 3, 10), date(2026, 12, 27), Decimal("31000"))
    assert len(payments) == 10
    assert payments[0].month == date(2026, 3, 1)
    assert payments[0].amount == Decimal("22000.00")  # 31000 * 22/31
    for p in payments[1:9]:
        assert p.amount == Decimal("31000")
    assert payments[-1].month == date(2026, 12, 1)
    assert payments[-1].amount == Decimal("27000.00")  # 31000 * 27/31
    assert sum((p.amount for p in payments), Decimal(0)) == Decimal("297000.00")


def test_calendar_month_payments_full_year_12_even_payments():
    payments = calendar_month_payments(date(2026, 1, 1), date(2026, 12, 31), Decimal("1000"))
    assert len(payments) == 12
    assert all(p.amount == Decimal("1000") for p in payments)


def test_calendar_month_payments_start_on_31st():
    payments = calendar_month_payments(date(2026, 1, 31), date(2026, 3, 1), Decimal("3000"))
    assert [p.month for p in payments] == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
    assert payments[0].amount == Decimal("96.77")  # 3000/31 * 1 день (31.01)
    assert payments[1].amount == Decimal("3000")   # февраль целиком
    assert payments[2].amount == Decimal("96.77")  # 3000/31 * 1 день (01.03)


def test_calendar_month_payments_leap_february():
    payments = calendar_month_payments(date(2028, 2, 1), date(2028, 2, 29), Decimal("2900"))
    assert len(payments) == 1
    assert payments[0].amount == Decimal("2900")  # полный месяц — 29 дней високосного февраля


def test_calendar_month_payments_end_before_start_is_empty():
    assert calendar_month_payments(date(2026, 5, 1), date(2026, 4, 1), Decimal("100")) == []


# ---------------------------------------------------------------------------
# Месяц заказа рамочного договора — по полю, по периоду, по порядку номеров.
# ---------------------------------------------------------------------------

async def _make_framework_order(
    db_session, subsidy_id, cat_id, parent_id, purchase_number, amount,
    status="contracted", planned_payment_month=None,
    service_start_date=None, service_end_date=None,
):
    p = Purchase(
        subsidy_id=subsidy_id, feo_category_id=cat_id, item_name="Заказ по рамочному",
        status=status, purchase_contract_type="framework_with_amount",
        parent_purchase_id=parent_id, purchase_number=purchase_number,
        contract_price=Decimal(str(amount)), total_nmck=Decimal(str(amount)), nmck=Decimal(str(amount)),
        planned_payment_month=planned_payment_month,
        service_start_date=service_start_date, service_end_date=service_end_date,
    )
    db_session.add(p)
    await db_session.flush()
    return p


async def _make_framework_head(db_session, subsidy_id):
    head = Purchase(
        subsidy_id=subsidy_id, item_name="Рамочный договор",
        status="contracted", purchase_contract_type="framework_with_amount",
    )
    db_session.add(head)
    await db_session.flush()
    return head


@pytest.mark.asyncio
async def test_framework_order_month_by_planned_payment_month_field(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    head = await _make_framework_head(db_session, subsidy.id)
    order = await _make_framework_order(
        db_session, subsidy.id, cat.id, head.id, 5, 1000,
        planned_payment_month=date(2026, 7, 14),  # любой день месяца — усекается до 1-го числа
    )
    await db_session.commit()

    rows = await framework_order_month_rows(db_session, [subsidy.id])
    assert len(rows) == 1
    assert rows[0]["month"] == date(2026, 7, 1)
    assert rows[0]["amount"] == pytest.approx(1000.0)


@pytest.mark.asyncio
async def test_framework_order_month_by_order_number_last_is_december(db_session, test_org):
    """Три заказа одного родителя без planned_payment_month/periода — месяц по
    порядку номеров, последний (самый большой purchase_number) = декабрь года
    субсидии, остальные — на месяц раньше каждый (владелец, пример ФАДМ:
    4 заказа сен-дек → contracted окт-дек)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    subsidy.year = 2026
    await db_session.commit()
    cat = await _make_category(db_session, subsidy.id)
    head = await _make_framework_head(db_session, subsidy.id)
    o1 = await _make_framework_order(db_session, subsidy.id, cat.id, head.id, 10, 100)
    o2 = await _make_framework_order(db_session, subsidy.id, cat.id, head.id, 11, 200)
    o3 = await _make_framework_order(db_session, subsidy.id, cat.id, head.id, 12, 300)
    await db_session.commit()

    rows = await framework_order_month_rows(db_session, [subsidy.id])
    by_purchase = {r["purchase_id"]: r["month"] for r in rows}
    assert by_purchase[o3.id] == date(2026, 12, 1)
    assert by_purchase[o2.id] == date(2026, 11, 1)
    assert by_purchase[o1.id] == date(2026, 10, 1)


@pytest.mark.asyncio
async def test_framework_order_month_by_order_number_ignores_stopped_siblings(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    subsidy.year = 2026
    await db_session.commit()
    cat = await _make_category(db_session, subsidy.id)
    head = await _make_framework_head(db_session, subsidy.id)
    o1 = await _make_framework_order(db_session, subsidy.id, cat.id, head.id, 1, 100)
    o2 = await _make_framework_order(db_session, subsidy.id, cat.id, head.id, 2, 200)
    o2.stopped_at = date(2026, 1, 1)
    await db_session.commit()

    rows = await framework_order_month_rows(db_session, [subsidy.id])
    # o2 остановлена (reserved_child_predicate её не возвращает вовсе,
    # committed_status_predicate у неё тоже не сработает — остановленные
    # закупки не считаются НИГДЕ) — o1 остаётся ЕДИНСТВЕННЫМ в выборке,
    # значит последним, месяц = декабрь.
    by_purchase = {r["purchase_id"]: r["month"] for r in rows}
    assert o2.id not in by_purchase
    assert by_purchase[o1.id] == date(2026, 12, 1)


@pytest.mark.asyncio
async def test_framework_order_month_by_service_period_splits_amount_by_days(db_session, test_org):
    """Источник 2 (план, п.B): заказ с periodом (без ставки в месяц) — сумма
    заказа делится по месяцам calendar_month_payments-пропорцией, НЕСКОЛЬКО
    строк на один заказ."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    head = await _make_framework_head(db_session, subsidy.id)
    order = await _make_framework_order(
        db_session, subsidy.id, cat.id, head.id, 1, 297000,
        service_start_date=date(2026, 3, 10), service_end_date=date(2026, 12, 27),
    )
    await db_session.commit()

    rows = await framework_order_month_rows(db_session, [subsidy.id])
    assert len(rows) == 10  # март..декабрь
    assert rows[0]["month"] == date(2026, 3, 1)
    assert rows[0]["amount"] == pytest.approx(22000.0)
    assert rows[-1]["month"] == date(2026, 12, 1)
    assert rows[-1]["amount"] == pytest.approx(27000.0)
    assert sum(r["amount"] for r in rows) == pytest.approx(297000.0)


# ---------------------------------------------------------------------------
# «Ещё уйдёт помесячно до конца года» — только будущие месяцы.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_monthly_future_rows_today_oct15_future_is_nov_dec(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    subsidy.year = 2026
    await db_session.commit()
    cat = await _make_category(db_session, subsidy.id)
    head = await _make_framework_head(db_session, subsidy.id)
    # 4 заказа сен-дек (владелец, пример «Егорова, уборка»): contracted окт-дек.
    orders = [
        await _make_framework_order(db_session, subsidy.id, cat.id, head.id, n, 27000)
        for n in range(1, 5)
    ]  # last (n=4) -> декабрь, n=3 -> ноябрь, n=2 -> октябрь, n=1 -> сентябрь
    await db_session.commit()

    today = date(2026, 10, 15)
    rows = await monthly_future_rows(db_session, [subsidy.id], today=today)
    months = sorted(r["month"] for r in rows)
    assert months == [date(2026, 11, 1), date(2026, 12, 1)]
    assert sum(r["amount"] for r in rows) == pytest.approx(54000.0)  # 2 x 27000


@pytest.mark.asyncio
async def test_monthly_future_rows_today_nov1_only_december(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    subsidy.year = 2026
    await db_session.commit()
    cat = await _make_category(db_session, subsidy.id)
    head = await _make_framework_head(db_session, subsidy.id)
    orders = [
        await _make_framework_order(db_session, subsidy.id, cat.id, head.id, n, 1000)
        for n in range(1, 5)
    ]
    await db_session.commit()

    today = date(2026, 11, 1)
    rows = await monthly_future_rows(db_session, [subsidy.id], today=today)
    months = sorted(r["month"] for r in rows)
    assert months == [date(2026, 12, 1)]
    totals = await monthly_future_totals_by_subsidy(db_session, [subsidy.id], today=today)
    assert totals[subsidy.id]["total"] == pytest.approx(1000.0)
    assert totals[subsidy.id]["framework_order"] == pytest.approx(1000.0)
    assert totals[subsidy.id]["monthly_contract"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Заказ начавшегося месяца — committed (дерево ФЭО), НЕ в «Можно
# перераспределить»; заказ будущего месяца — наоборот.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_started_month_order_is_committed_and_excluded_from_redistributable(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=100_000)
    subsidy.year = 2026
    await db_session.commit()
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_planned_item(db_session, cat.id, "Связь", 1, 100_000)
    await db_session.commit()

    head = await _make_framework_head(db_session, subsidy.id)
    # Единственный заказ договора -> месяц = декабрь года субсидии (2026).
    order = await _make_framework_order(db_session, subsidy.id, cat.id, head.id, 1, 100_000)
    await db_session.commit()
    pi = PurchaseItem(
        purchase_id=order.id, item_name="Связь", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("100000"), total_price=Decimal("100000"), item_type="услуга",
        feo_category_id=cat.id, feo_planned_item_id=item.id, over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()

    # today = декабрь (месяц уже начался) -> committed; today = ноябрь
    # (месяц ещё не начался) -> НЕ committed, «ещё уйдёт».
    from app.services.committed_amounts import committed_by_planned_item

    committed_dec = await committed_by_planned_item(
        db_session, [item.id], month_aware=True,
    )
    # committed_by_planned_item сам берёт date.today() когда today не передан
    # в committed_status_predicate — здесь передаём явно через флаг месяца:
    # имитация «уже декабрь» делается прямой проверкой SQL-предиката с today=.
    from app.services.committed_amounts import committed_status_predicate
    from app.models.subsidy import Subsidy as _Subsidy
    from sqlalchemy import select as _select

    stmt_dec = (
        _select(Purchase.id)
        .join(_Subsidy, _Subsidy.id == Purchase.subsidy_id)
        .where(committed_status_predicate(Purchase, subsidy_year_col=_Subsidy.year, today=date(2026, 12, 15)))
        .where(Purchase.id == order.id)
    )
    assert (await db_session.execute(stmt_dec)).first() is not None  # committed в декабре

    stmt_nov = (
        _select(Purchase.id)
        .join(_Subsidy, _Subsidy.id == Purchase.subsidy_id)
        .where(committed_status_predicate(Purchase, subsidy_year_col=_Subsidy.year, today=date(2026, 11, 15)))
        .where(Purchase.id == order.id)
    )
    assert (await db_session.execute(stmt_nov)).first() is None  # ещё НЕ committed в ноябре

    # «Можно перераспределить» — при today=декабрь заказ уже committed, raw=0,
    # ничего не уходит в monthly_future_not_started; при today=ноябрь (default
    # сегодняшней даты теста не используем — not_committed_raw_by_subsidy
    # принимает today) заказ будущего месяца (декабрь) уходит в monthly_future_not_started.
    raw_nov = await not_committed_raw_by_subsidy(db_session, [subsidy.id], today=date(2026, 11, 15))
    assert raw_nov[subsidy.id]["likely_raw"] == pytest.approx(0.0)
    assert raw_nov[subsidy.id]["monthly_future_not_started_raw"] == pytest.approx(100_000.0)


# ---------------------------------------------------------------------------
# Инвариант четырёх строк карточки «Можно перераспределить».
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_four_rows_invariant_sums_to_redistributable(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=500_000)
    subsidy.year = 2026
    await db_session.commit()
    cat = await _make_category(db_session, subsidy.id)

    item_nice = await _make_planned_item(db_session, cat.id, "Хотелось бы", 1, 100_000)
    item_nice.need_level = "nice_to_have"
    item_likely = await _make_planned_item(db_session, cat.id, "Скорее всего", 1, 150_000)
    item_framework = await _make_planned_item(db_session, cat.id, "Связь", 1, 250_000)
    await db_session.commit()

    head = await _make_framework_head(db_session, subsidy.id)
    order = await _make_framework_order(db_session, subsidy.id, cat.id, head.id, 1, 250_000)
    await db_session.commit()
    pi = PurchaseItem(
        purchase_id=order.id, item_name="Связь", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("250000"), total_price=Decimal("250000"), item_type="услуга",
        feo_category_id=cat.id, feo_planned_item_id=item_framework.id, over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]
    assert row["redistributable_unplanned"] + row["not_committed_nice"] \
        + row["not_committed_likely"] + row["monthly_future_not_started"] \
        == pytest.approx(row["redistributable"])
    # Заказ единственный -> декабрь 2026 (будущее относительно даты прогона
    # теста, т.к. система уже в 2026 году) -> не начат -> строка 4.
    assert row["monthly_future_not_started"] == pytest.approx(250_000.0)
    assert row["not_committed_likely"] == pytest.approx(150_000.0)
    assert row["not_committed_nice"] == pytest.approx(100_000.0)


# ---------------------------------------------------------------------------
# Видимость чужой субсидии — subsidy_ids ограничивает выборку.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_monthly_future_rows_respects_subsidy_ids_scope(db_session, test_org):
    subsidy_a = await _make_subsidy(db_session, test_org.id)
    subsidy_b = await _make_subsidy(db_session, test_org.id)
    for s in (subsidy_a, subsidy_b):
        s.year = 2026
    await db_session.commit()
    cat_a = await _make_category(db_session, subsidy_a.id)
    cat_b = await _make_category(db_session, subsidy_b.id)
    head_a = await _make_framework_head(db_session, subsidy_a.id)
    head_b = await _make_framework_head(db_session, subsidy_b.id)
    await _make_framework_order(db_session, subsidy_a.id, cat_a.id, head_a.id, 1, 1000)
    await _make_framework_order(db_session, subsidy_b.id, cat_b.id, head_b.id, 1, 2000)
    await db_session.commit()

    totals = await monthly_future_totals_by_subsidy(db_session, [subsidy_a.id], today=date(2026, 1, 1))
    assert subsidy_b.id not in totals
    assert totals[subsidy_a.id]["framework_order"] == pytest.approx(1000.0)
