"""Тесты app/services/type_totals.py (план ancient-prancing-music.md, раздел B/2).

Инвариант владельца (Правило №6): план_goods+plan_services+plan_unspecified
обязана РОВНО совпадать с тем, как общий план субсидии считает существующий
код (app.routers.subsidies._calculate_planned_amounts_bulk — Σ активных
FeoPlannedItem.amount). Аналогично feo_goods+feo_services+feo_unspecified
обязана совпадать с calculate_budgets_bulk (subsidy_budget.py) на дереве без
собственного subsidy.budget (calc из категорий).
"""
import uuid
from decimal import Decimal

import pytest

from app.routers.subsidies import _calculate_planned_amounts_bulk, calculate_budgets_bulk
from app.services.type_totals import effective_item_types, subsidy_type_totals


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"TypeTotalsSubsidy-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, budget=None):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(subsidy_id=subsidy_id, parent_id=None, level=1, name=f"Cat-{uuid.uuid4().hex[:8]}", budget=budget)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, item_type, amount, feo_amount=None, is_active=True):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=f"Item-{uuid.uuid4().hex[:8]}",
        item_type=item_type,
        amount=Decimal(str(amount)),
        feo_amount=Decimal(str(feo_amount)) if feo_amount is not None else None,
        is_active=is_active,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _link_purchase_item(db_session, feo_planned_item_id, item_type, status="plan_schedule"):
    """Позиция закупки, связанная с плановой позицией через feo_planned_item_id —
    источник наследования типа (effective_item_types)."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    p = Purchase(status=status, item_name="linked purchase", planned_total_price=Decimal("10"))
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id, item_name="linked item", item_type=item_type,
        quantity=Decimal("1"), unit_price=Decimal("10"), total_price=Decimal("10"),
        feo_planned_item_id=feo_planned_item_id,
    )
    db_session.add(pi)
    await db_session.commit()
    return p, pi


@pytest.mark.asyncio
class TestSubsidyTypeTotals:
    async def test_plan_split_matches_existing_planned_amounts(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id)  # no explicit budget
        await _make_planned_item(db_session, cat.id, "товар", 100, feo_amount=90)
        await _make_planned_item(db_session, cat.id, "услуга", 200)
        await _make_planned_item(db_session, cat.id, None, 50)

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]

        assert t["plan_goods"] == pytest.approx(100.0)
        assert t["plan_services"] == pytest.approx(200.0)
        assert t["plan_unspecified"] == pytest.approx(50.0)

        existing_plan = (await _calculate_planned_amounts_bulk(db_session, [subsidy.id]))[subsidy.id]
        assert t["plan_goods"] + t["plan_services"] + t["plan_unspecified"] == pytest.approx(existing_plan)
        assert existing_plan == pytest.approx(350.0)

    async def test_feo_split_matches_existing_budget(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id)
        # только первая позиция несёт feo_amount (90, товар) — единственный
        # вклад в «по ФЭО» категории (см. compute_budget_map: категория без
        # собственного budget = Σ feo_amount собственных активных позиций).
        await _make_planned_item(db_session, cat.id, "товар", 100, feo_amount=90)
        await _make_planned_item(db_session, cat.id, "услуга", 200)
        await _make_planned_item(db_session, cat.id, None, 50)

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]

        assert t["feo_goods"] == pytest.approx(90.0)
        assert t["feo_services"] == pytest.approx(0.0)
        assert t["feo_unspecified"] == pytest.approx(0.0)

        existing_budget = (await calculate_budgets_bulk(db_session, [subsidy.id]))[subsidy.id]
        assert t["feo_goods"] + t["feo_services"] + t["feo_unspecified"] == pytest.approx(existing_budget)
        assert existing_budget == pytest.approx(90.0)

    async def test_category_explicit_budget_goes_to_unspecified(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id, budget=500)
        # Позиция с типом ЕСТЬ, но она НЕ участвует в «по ФЭО» — категория имеет
        # собственную явную budget, которая главнее (compute_budget_map) и не
        # помечена типом — идёт целиком в feo_unspecified.
        await _make_planned_item(db_session, cat.id, "товар", 100, feo_amount=90)

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]
        assert t["feo_goods"] == pytest.approx(0.0)
        assert t["feo_unspecified"] == pytest.approx(500.0)
        existing_budget = (await calculate_budgets_bulk(db_session, [subsidy.id]))[subsidy.id]
        assert existing_budget == pytest.approx(500.0)

    async def test_inherited_type_from_linked_purchase_item(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id)
        fpi = await _make_planned_item(db_session, cat.id, None, 30)  # no own type
        await _link_purchase_item(db_session, fpi.id, "услуга")

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]
        assert t["plan_services"] == pytest.approx(30.0)
        assert t["plan_goods"] == pytest.approx(0.0)
        assert t["plan_unspecified"] == pytest.approx(0.0)

    async def test_conflicting_inherited_types_stay_unspecified(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id)
        fpi = await _make_planned_item(db_session, cat.id, None, 40)
        await _link_purchase_item(db_session, fpi.id, "товар")
        await _link_purchase_item(db_session, fpi.id, "услуга")

        types = await effective_item_types(db_session, [fpi.id])
        assert types.get(fpi.id) is None  # разные типы — не выдумываем

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]
        assert t["plan_unspecified"] == pytest.approx(40.0)

    async def test_empty_subsidy_ids(self, db_session):
        assert await subsidy_type_totals(db_session, []) == {}

    async def test_inactive_planned_items_excluded(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id)
        await _make_planned_item(db_session, cat.id, "товар", 100, is_active=False)

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]
        assert t["plan_goods"] == pytest.approx(0.0)
        existing_plan = (await _calculate_planned_amounts_bulk(db_session, [subsidy.id]))[subsidy.id]
        assert existing_plan == pytest.approx(0.0)
