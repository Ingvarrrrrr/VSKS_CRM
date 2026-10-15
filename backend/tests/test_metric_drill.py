"""test_metric_drill.py — GET /api/dashboard/metric-drill и построчные функции
app.services.metric_drill_rows (план abstract-noodling-pelican.md, 15.10.2026,
п.5 техчасти): по каждой метрике Σ rows["amount"] ОБЯЗАНА совпасть с
card_total (ПРАВИЛО №6 — не вторая формула, см. докстринг модуля), плюс
kind=all в dashboard_type_drill.py и видимость чужой субсидии (пусто)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.metric_drill_rows import (
    balance_drill,
    economy_drill,
    monthly_future_drill,
    monthly_future_not_started_drill,
    not_committed_level_drill,
    paid_drill,
)
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


async def _make_framework_order(db_session, subsidy_id, feo_category_id, feo_planned_item_id,
                                 head, purchase_number, planned_payment_month=None, amount=10_000):
    p = Purchase(
        subsidy_id=subsidy_id, feo_category_id=feo_category_id, item_name="Заказ по рамочному",
        status="contracted", purchase_contract_type="framework_with_amount",
        parent_purchase_id=head.id, purchase_number=purchase_number,
        planned_payment_month=planned_payment_month,
        contract_price=Decimal(str(amount)), total_nmck=Decimal(str(amount)), nmck=Decimal(str(amount)),
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id, item_name="Связь", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal(str(amount)), total_price=Decimal(str(amount)), item_type="услуга",
        feo_category_id=feo_category_id, feo_planned_item_id=feo_planned_item_id, over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_monthly_future_drill_matches_card_total(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1)
    cat = await _make_category(db_session, subsidy.id, name="Связь")
    item = await _make_planned_item(db_session, cat.id, "Связь по рамочному", 1, 100_000)

    head = Purchase(
        subsidy_id=subsidy.id, item_name="Рамочный договор (связь)",
        status="contracted", purchase_contract_type="framework_with_amount",
    )
    db_session.add(head)
    await db_session.flush()
    await db_session.commit()

    future_month = date(date.today().year, 12, 1) if date.today().month < 12 else None
    if future_month is None:
        pytest.skip("тест предполагает текущий месяц раньше декабря")

    await _make_framework_order(
        db_session, subsidy.id, cat.id, item.id, head, purchase_number=1,
        planned_payment_month=future_month, amount=23_000,
    )

    result = await monthly_future_drill(db_session, [subsidy.id])
    assert result["total"] == pytest.approx(result["card_total"])
    assert result["card_total"] == pytest.approx(23_000.0)
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["row_type"] == "month"
    assert row["amount"] == pytest.approx(23_000.0)
    assert row["month"] == future_month.isoformat()
    assert row["source"] == "framework_order"


@pytest.mark.asyncio
async def test_monthly_future_not_started_drill_matches_card_total(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1)
    cat = await _make_category(db_session, subsidy.id, name="Связь")
    item = await _make_planned_item(db_session, cat.id, "Связь по рамочному", 1, 40_000)

    head = Purchase(
        subsidy_id=subsidy.id, item_name="Рамочный договор (связь)",
        status="contracted", purchase_contract_type="framework_with_amount",
    )
    db_session.add(head)
    await db_session.flush()
    await db_session.commit()

    future_month = date(date.today().year, 12, 1) if date.today().month < 12 else None
    if future_month is None:
        pytest.skip("тест предполагает текущий месяц раньше декабря")

    order = await _make_framework_order(
        db_session, subsidy.id, cat.id, item.id, head, purchase_number=1,
        planned_payment_month=future_month, amount=40_000,
    )

    result = await monthly_future_not_started_drill(db_session, [subsidy.id])
    assert result["total"] == pytest.approx(result["card_total"])
    assert result["card_total"] == pytest.approx(40_000.0)
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["row_type"] == "planned_item"
    assert row["planned_item_id"] == item.id
    assert row["amount"] == pytest.approx(40_000.0)
    assert len(row["orders"]) == 1
    assert row["orders"][0]["purchase_id"] == order.id
    assert row["orders"][0]["month"] == future_month.isoformat()


@pytest.mark.asyncio
async def test_not_committed_nice_and_likely_drill_match_card(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1)
    cat = await _make_category(db_session, subsidy.id, name="Товары и услуги")

    item_nice = await _make_planned_item(db_session, cat.id, "Хотелось бы", 1, 100_000)
    item_nice.need_level = "nice_to_have"
    item_likely = await _make_planned_item(db_session, cat.id, "Скорее всего", 1, 60_000)
    item_likely.need_level = "likely"
    await db_session.commit()

    nice_result = await not_committed_level_drill(db_session, [subsidy.id], "not_committed_nice")
    assert nice_result["total"] == pytest.approx(nice_result["card_total"])
    assert nice_result["card_total"] == pytest.approx(100_000.0)
    assert len(nice_result["rows"]) == 1
    assert nice_result["rows"][0]["planned_item_id"] == item_nice.id

    likely_result = await not_committed_level_drill(db_session, [subsidy.id], "not_committed_likely")
    assert likely_result["total"] == pytest.approx(likely_result["card_total"])
    assert likely_result["card_total"] == pytest.approx(60_000.0)
    assert len(likely_result["rows"]) == 1
    assert likely_result["rows"][0]["planned_item_id"] == item_likely.id


@pytest.mark.asyncio
async def test_paid_drill_declared_and_confirmed_match_card(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1)
    cat = await _make_category(db_session, subsidy.id, name="Товары")

    p = Purchase(
        subsidy_id=subsidy.id, feo_category_id=cat.id, item_name="Бензопила",
        status="work_in_progress",
        payment_amount=Decimal("30000"),            # подтверждено выпиской
        payment_amount_declared=Decimal("5000"),     # ещё по отметке, не подтверждено
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id, item_name="Бензопила", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("35000"), total_price=Decimal("35000"), item_type="товар",
        feo_category_id=cat.id,
    )
    db_session.add(pi)
    await db_session.commit()

    declared = await paid_drill(db_session, [subsidy.id], "paid_declared")
    assert declared["total"] == pytest.approx(declared["card_total"])
    assert declared["card_total"] == pytest.approx(35_000.0)  # 30000 + 5000

    confirmed = await paid_drill(db_session, [subsidy.id], "paid_confirmed")
    assert confirmed["total"] == pytest.approx(confirmed["card_total"])
    assert confirmed["card_total"] == pytest.approx(30_000.0)

    # kind=goods — вся сумма "товар", Σ строк тоже должна сойтись с card_total.
    declared_goods = await paid_drill(db_session, [subsidy.id], "paid_declared", kind="goods")
    assert declared_goods["total"] == pytest.approx(declared_goods["card_total"])
    assert declared_goods["card_total"] == pytest.approx(35_000.0)


@pytest.mark.asyncio
async def test_balance_drill_matches_card(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=500_000)
    cat = await _make_category(db_session, subsidy.id, name="Товары")  # корневая категория (parent_id=None)

    p = Purchase(
        subsidy_id=subsidy.id, feo_category_id=cat.id, item_name="Бензопила",
        status="work_in_progress",
        payment_amount=Decimal("20000"),
        payment_amount_declared=Decimal("3000"),
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id, item_name="Бензопила", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("23000"), total_price=Decimal("23000"), item_type="товар",
        feo_category_id=cat.id,
    )
    db_session.add(pi)
    await db_session.commit()

    marked = await balance_drill(db_session, [subsidy.id], "balance_marked")
    assert marked["total"] == pytest.approx(marked["card_total"])
    budget_row = next(r for r in marked["rows"] if r["row_type"] == "budget")
    purchase_rows = [r for r in marked["rows"] if r["row_type"] == "purchase"]
    assert budget_row["amount"] == pytest.approx(500_000.0)
    assert sum(r["amount"] for r in purchase_rows) == pytest.approx(-23_000.0)
    assert marked["card_total"] == pytest.approx(500_000.0 - 23_000.0)

    confirmed = await balance_drill(db_session, [subsidy.id], "balance_confirmed")
    assert confirmed["total"] == pytest.approx(confirmed["card_total"])
    assert confirmed["card_total"] == pytest.approx(500_000.0 - 20_000.0)


@pytest.mark.asyncio
async def test_economy_drill_matches_card(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    cat = await _make_category(db_session, subsidy.id, name="Техника")
    fpi = await _make_planned_item(db_session, cat.id, "Бензопила", 2, 200_000)  # 100 000/шт план

    await _make_linked_purchase(db_session, subsidy.id, cat.id, fpi.id, 1, 90_000, planned_total=Decimal("100000"))

    result = await economy_drill(db_session, [subsidy.id])
    assert result["total"] == pytest.approx(result["card_total"])
    assert result["card_total"] == pytest.approx(10_000.0)  # 100 000 план - 90 000 факт
    assert len(result["rows"]) == 1
    assert result["rows"][0]["amount"] == pytest.approx(10_000.0)


@pytest.mark.asyncio
async def test_metric_drill_foreign_subsidy_not_visible(db_session, test_org):
    """Субсидия, не входящая в переданный subsidy_ids/видимость — отсутствует
    в выдаче: на уровне сервиса достаточно не передавать её id в список."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1)
    await _make_category(db_session, subsidy.id, name="Чужая")

    result = await not_committed_level_drill(db_session, [], "not_committed_nice")
    assert result["rows"] == []
    assert result["total"] == 0
    assert result["card_total"] == 0


@pytest.mark.asyncio
async def test_type_drill_kind_all(client, superadmin_headers, db_session, test_org):
    """kind=all карточки стадии — все строки без фильтра по товар/услуга, с
    items_text/supplier по общему хелперу purchase_drill_text."""
    from app.models.contractor import Contractor

    subsidy = await _make_subsidy(db_session, test_org.id, budget=1)
    cat = await _make_category(db_session, subsidy.id, name="Смешанное")

    contractor = Contractor(name="ООО Ромашка")
    db_session.add(contractor)
    await db_session.flush()

    p = Purchase(
        subsidy_id=subsidy.id, feo_category_id=cat.id, item_name="Канцтовары",
        status="work_in_progress", contractor_id=contractor.id,
    )
    db_session.add(p)
    await db_session.flush()
    pi_goods = PurchaseItem(
        purchase_id=p.id, item_name="Бумага А4", quantity=Decimal("10"), unit="шт",
        unit_price=Decimal("500"), total_price=Decimal("5000"), item_type="товар",
        feo_category_id=cat.id,
    )
    pi_services = PurchaseItem(
        purchase_id=p.id, item_name="Доставка", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("1000"), total_price=Decimal("1000"), item_type="услуга",
        feo_category_id=cat.id,
    )
    db_session.add_all([pi_goods, pi_services])
    await db_session.commit()

    resp_all = await client.get(
        "/api/dashboard/type-drill",
        params={"stage": "work", "kind": "all", "scope": "dashboard",
                "subsidy_ids": str(subsidy.id)},
        headers=superadmin_headers,
    )
    assert resp_all.status_code == 200
    body_all = resp_all.json()

    resp_goods = await client.get(
        "/api/dashboard/type-drill",
        params={"stage": "work", "kind": "goods", "scope": "dashboard",
                "subsidy_ids": str(subsidy.id)},
        headers=superadmin_headers,
    )
    resp_services = await client.get(
        "/api/dashboard/type-drill",
        params={"stage": "work", "kind": "services", "scope": "dashboard",
                "subsidy_ids": str(subsidy.id)},
        headers=superadmin_headers,
    )
    body_goods = resp_goods.json()
    body_services = resp_services.json()

    assert body_all["total"] == pytest.approx(body_goods["total"] + body_services["total"])
    assert len(body_all["rows"]) == len(body_goods["rows"]) + len(body_services["rows"])

    row = body_all["rows"][0]
    assert row["supplier"] == "ООО Ромашка"
    assert "Бумага А4" in row["items_text"] or "Доставка" in row["items_text"]
