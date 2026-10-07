"""«Приравнять ФЭО к плану по всем статьям» одним действием (решение
владельца 07.10.2026, план .planning/quick/2026-10-07-dnr-feo-cards/PLAN.md
шаг 3, решение владельца №4) — app.services.feo_tree_write.
align_budget_to_plan_all + POST /api/subsidies/{id}/feo/align-budget-to-
plan-all (app.routers.feo_tree_ops.router_subsidy_feo).

Переиспользует фабрики test_align_budget_to_plan_ceiling_error.py (ПРАВИЛО
№6 — не второй набор фабрик)."""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import feo_tree_write
from tests.test_align_budget_to_plan_ceiling_error import _make_category, _make_planned_item, _make_subsidy


def _mk_admin_user(org_id):
    return SimpleNamespace(role="org_admin", id=1, org_id=org_id, _active_org_id=org_id, _uoa_org_ids=[])


@pytest.mark.asyncio
async def test_align_all_sets_budget_equal_to_plan_everywhere(db_session, test_org):
    """41-статья сценарий ДНР упрощённо: несколько статей без ФЭО, разный
    план. После align-all budget == plan у КАЖДОЙ статьи, count == число
    статей с планом (без изменений не считаем), total == Σ плана."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    cat_a = await _make_category(db_session, subsidy.id, name="Статья А", budget=None)
    cat_b = await _make_category(db_session, subsidy.id, name="Статья Б", budget=None)
    cat_c = await _make_category(db_session, subsidy.id, name="Статья В (уже верно)", budget=Decimal("5000"))
    await _make_planned_item(db_session, cat_a.id, amount=100_000)
    await _make_planned_item(db_session, cat_b.id, amount=50_000)
    await _make_planned_item(db_session, cat_c.id, amount=5_000)  # уже равно budget

    user = _mk_admin_user(test_org.id)
    result = await feo_tree_write.align_budget_to_plan_all(db_session, user, subsidy.id)
    await db_session.commit()

    assert result["count"] == 2  # cat_a и cat_b изменились, cat_c уже была равна
    assert result["total"] == pytest.approx(155_000.0)

    for cat, expected in ((cat_a, 100_000.0), (cat_b, 50_000.0), (cat_c, 5_000.0)):
        await db_session.refresh(cat)
        assert float(cat.budget) == pytest.approx(expected)


@pytest.mark.asyncio
async def test_align_all_empty_subsidy_returns_zero(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    user = _mk_admin_user(test_org.id)
    result = await feo_tree_write.align_budget_to_plan_all(db_session, user, subsidy.id)
    assert result == {"count": 0, "total": 0.0}


@pytest.mark.asyncio
async def test_align_single_category_succeeds_while_rest_of_subsidy_has_no_feo(db_session, test_org):
    """Решение владельца №4 (найдено на «ДНР»): «Приравнять» на ОДНОЙ статье
    работает без отказа, когда у ОСТАЛЬНЫХ статей субсидии ФЭО вовсе не
    введено — статьи без ФЭО не участвуют в проверке потолка (см.
    app.services.subsidy_budget.feo_entered_ceiling_and_plan,
    test_align_budget_to_plan_ceiling_error.py)."""
    from app.routers.feo_tree_ops import align_budget_to_plan

    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    cat_target = await _make_category(db_session, subsidy.id, name="День спасателя", budget=None)
    cat_rest_1 = await _make_category(db_session, subsidy.id, name="Статья без ФЭО 1", budget=None)
    cat_rest_2 = await _make_category(db_session, subsidy.id, name="Статья без ФЭО 2", budget=None)
    await _make_planned_item(db_session, cat_target.id, amount=185_000)
    await _make_planned_item(db_session, cat_rest_1.id, amount=30_000_000)
    await _make_planned_item(db_session, cat_rest_2.id, amount=33_000_000)

    user = _mk_admin_user(test_org.id)
    result = await align_budget_to_plan(cat_target.id, db=db_session, current_user=user)

    assert result["new_budget"] == pytest.approx(185_000.0)
    assert result["subsidy_over_before"] == pytest.approx(0.0)
    assert result["subsidy_over_after"] == pytest.approx(0.0)
