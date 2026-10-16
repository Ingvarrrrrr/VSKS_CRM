# -*- coding: utf-8 -*-
"""Раскраска плановых позиций дерева ФЭО по стадии закупки (владелец,
16.10.2026) — app.services.plan_item_stage. Переиспользует фабрики
_make_subsidy/_make_category из test_feo_plan_tree_scenarios.py (ПРАВИЛО №6,
вторая копия не заводится), сценарий закупки — тот же приём, что и
test_paid_confirmed_vs_declared_tree.py::_make_purchase_with_payment.
"""
from decimal import Decimal

import pytest

from app.models.feo_planned_item import FeoPlannedItem
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.feo_plan_payments import (
    paid_consumption_by_category,
    purchase_item_payment_amounts,
)
from app.services.plan_item_stage import (
    STAGE_ORDERED,
    STAGE_PAID_CONFIRMED,
    STAGE_PAID_MARKED,
    category_plan_stage_segments,
    planned_item_stage_segments,
)
from app.services.purchase_payments import recompute_purchase_payments
from tests.test_feo_plan_tree_scenarios import _make_category, _make_subsidy


async def _make_purchase_item(
    db_session, subsidy_id, feo_category_id, planned_item_id, quantity, unit_price, status,
):
    amount = Decimal(str(quantity)) * Decimal(str(unit_price))
    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        item_name="Комбинезон",
        status=status,
        contract_price=amount,
        total_nmck=amount,
        nmck=amount,
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id,
        item_name="Комбинезон",
        quantity=Decimal(str(quantity)),
        unit="шт",
        unit_price=Decimal(str(unit_price)),
        total_price=amount,
        feo_category_id=feo_category_id,
        feo_planned_item_id=planned_item_id,
        over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(p)
    return p, pi


@pytest.mark.asyncio
async def test_two_purchases_split_segments_by_share(db_session, test_org):
    """200 = 100 delivered + 100 ordered → две полосы (по закупке), по 0.5
    каждая, обе — стадия 'ordered' (ordered/delivered — один шаг шкалы)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="Комбинезоны", budget=Decimal("200000"))
    planned_item = FeoPlannedItem(
        feo_category_id=leaf.id, name="Комбинезон", quantity=Decimal("200"),
        unit_price=Decimal("1000"), amount=Decimal("200000"), is_active=True,
    )
    db_session.add(planned_item)
    await db_session.commit()
    await db_session.refresh(planned_item)

    await _make_purchase_item(db_session, subsidy.id, leaf.id, planned_item.id, 100, 1000, "delivered")
    await _make_purchase_item(db_session, subsidy.id, leaf.id, planned_item.id, 100, 1000, "ordered")

    result = await planned_item_stage_segments(db_session, [planned_item.id])
    data = result[planned_item.id]
    assert data["overflow"] is False
    segments = data["segments"]
    assert len(segments) == 2
    assert {round(s["share"], 4) for s in segments} == {0.5}
    assert {s["stage"] for s in segments} == {STAGE_ORDERED}


@pytest.mark.asyncio
async def test_partial_quantity_leaves_remainder_empty(db_session, test_org):
    """150 из 200 (100 delivered + 50 ordered) → доли 0.5 + 0.25, остаток 0.25
    не закрыт ни одним сегментом (сумма долей < 1, без overflow)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="Комбинезоны", budget=Decimal("200000"))
    planned_item = FeoPlannedItem(
        feo_category_id=leaf.id, name="Комбинезон", quantity=Decimal("200"),
        unit_price=Decimal("1000"), amount=Decimal("200000"), is_active=True,
    )
    db_session.add(planned_item)
    await db_session.commit()
    await db_session.refresh(planned_item)

    await _make_purchase_item(db_session, subsidy.id, leaf.id, planned_item.id, 100, 1000, "delivered")
    await _make_purchase_item(db_session, subsidy.id, leaf.id, planned_item.id, 50, 1000, "ordered")

    result = await planned_item_stage_segments(db_session, [planned_item.id])
    data = result[planned_item.id]
    assert data["overflow"] is False
    shares = sorted(round(s["share"], 4) for s in data["segments"])
    assert shares == [0.25, 0.5]
    assert sum(shares) == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_payment_marked_vs_confirmed_stage(db_session, test_org):
    """Оплата закупки целиком по позиции — отметкой поднимает до paid_marked,
    подтверждение выпиской — до paid_confirmed (владелец: «частичная оплата —
    стадия по статусу закупки», здесь оплата полная)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="Комбинезоны", budget=Decimal("200000"))
    planned_item = FeoPlannedItem(
        feo_category_id=leaf.id, name="Комбинезон", quantity=Decimal("2"),
        unit_price=Decimal("100"), amount=Decimal("200"), is_active=True,
    )
    db_session.add(planned_item)
    await db_session.commit()
    await db_session.refresh(planned_item)

    purchase_marked, _ = await _make_purchase_item(
        db_session, subsidy.id, leaf.id, planned_item.id, 1, 100, "delivered",
    )
    pay_marked = Payment(
        purchase_id=purchase_marked.id, amount=Decimal("100"),
        payment_source="manual", confirmed_by_statement=False,
    )
    db_session.add(pay_marked)
    await db_session.commit()
    await recompute_purchase_payments(db_session, purchase_marked.id)
    await db_session.commit()

    purchase_confirmed, _ = await _make_purchase_item(
        db_session, subsidy.id, leaf.id, planned_item.id, 1, 100, "delivered",
    )
    pay_confirmed = Payment(
        purchase_id=purchase_confirmed.id, amount=Decimal("100"),
        payment_source="statement", confirmed_by_statement=True, matched_confirmed=True,
    )
    db_session.add(pay_confirmed)
    await db_session.commit()
    await recompute_purchase_payments(db_session, purchase_confirmed.id)
    await db_session.commit()

    result = await planned_item_stage_segments(db_session, [planned_item.id])
    segments = result[planned_item.id]["segments"]
    by_purchase = {s["purchase_id"]: s["stage"] for s in segments}
    assert by_purchase[purchase_marked.id] == STAGE_PAID_MARKED
    assert by_purchase[purchase_confirmed.id] == STAGE_PAID_CONFIRMED


@pytest.mark.asyncio
async def test_category_segments_sum_of_payments_matches_category_total(db_session, test_org):
    """Σ paid_marked/paid_confirmed по сегментам category_plan_stage_segments
    (через purchase_item_payment_amounts) совпадает с paid_consumption_by_category
    — тот же источник (ПРАВИЛО №6), второй расчёт оплаты не заводится."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="Без Ур.5", budget=Decimal("1000"))

    p1, _ = await _make_purchase_item(db_session, subsidy.id, leaf.id, None, 1, 100, "delivered")
    pay1 = Payment(purchase_id=p1.id, amount=Decimal("100"), payment_source="statement", confirmed_by_statement=True)
    db_session.add(pay1)
    await db_session.commit()
    await recompute_purchase_payments(db_session, p1.id)
    await db_session.commit()

    p2, _ = await _make_purchase_item(db_session, subsidy.id, leaf.id, None, 1, 50, "delivered")
    pay2 = Payment(purchase_id=p2.id, amount=Decimal("50"), payment_source="manual", confirmed_by_statement=False)
    db_session.add(pay2)
    await db_session.commit()
    await recompute_purchase_payments(db_session, p2.id)
    await db_session.commit()

    by_cat = await paid_consumption_by_category(db_session, [subsidy.id])
    cat_totals = by_cat[leaf.id]

    item_amounts = await purchase_item_payment_amounts(db_session, [p1.id, p2.id])
    summed_marked = sum(v["paid_marked"] for v in item_amounts.values())
    summed_confirmed = sum(v["paid_confirmed"] for v in item_amounts.values())
    assert summed_marked == pytest.approx(cat_totals["paid_marked"])
    assert summed_confirmed == pytest.approx(cat_totals["paid_confirmed"])

    segments_result = await category_plan_stage_segments(db_session, [leaf.id])
    seg = segments_result[leaf.id]["segments"]
    assert len(seg) == 2
    stages = {s["purchase_id"]: s["stage"] for s in seg}
    assert stages[p1.id] == STAGE_PAID_CONFIRMED
    assert stages[p2.id] == STAGE_PAID_MARKED
