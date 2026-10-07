"""Решение владельца 07.10.2026 (план .planning/quick/2026-10-07-dnr-feo-
cards/PLAN.md шаг 1, решение №3, найдено на субсидии «ДНР»): пока ФЭО не
введено ни у одной статьи субсидии, карточка «Бюджет (ФЭО)» пишет «ФЭО не
введено», без суммы и разбивки — ОТМЕНЕНО решение 06.10.2026 («бюджет =
план», которое к тому же теряло позиции, привязанные прямо к статье с
подкатегориями — см. test_feo_category_with_subcategories_and_own_items).

Переиспользует фабрики test_feo_plan_tree_scenarios.py (ПРАВИЛО №6)."""
from decimal import Decimal

import pytest

from app.services.feo_plan_tree import compute_feo_plan_tree
from app.services.subsidy_money_summary import subsidy_money_summary
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


@pytest.mark.asyncio
async def test_subsidy_without_feo_anywhere_budget_card_is_empty(db_session, test_org):
    """41 статья, ни у одной не введено ФЭО (как «ДНР») — budget_basis/
    free_basis/redistributable*/balance_* = None, feo_entered=False.
    «Запланировано» считается как обычно (не затронуто решением №3)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    for i in range(3):
        cat = await _make_category(db_session, subsidy.id, name=f"Статья {i+1} (без ФЭО)")
        await _make_planned_item(db_session, cat.id, f"Позиция {i+1}", 1, 100_000)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["feo_entered"] is False
    assert row["budget_basis"] is None
    assert row["free_basis"] is None
    assert row["redistributable"] is None
    assert row["redistributable_by_kind"] is None
    assert row["redistributable_unplanned"] is None
    assert row["balance_by_marks"] is None
    assert row["balance_by_statement"] is None
    assert row["budget_from_plan"] is False  # подмена планом отменена целиком
    # «Запланировано» не трогается решением №3.
    assert row["planned"] == pytest.approx(300_000.0)


@pytest.mark.asyncio
async def test_feo_category_with_subcategories_and_own_items(db_session, test_org):
    """Боевая причина 8 191,49 (ДНР): позиции, привязанные ПРЯМО к статье,
    у которой есть подстатьи, не смеют теряться из суммы дерева. Статья
    «Оргтехника» имеет подстатью «Мебель» (план 50 000) и свои собственные
    позиции «Чайник» (1 904,45) + «Термопот» (6 287,04) — план статьи
    (node['display']) обязан включать ВСЕ три числа."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    parent = await _make_category(db_session, subsidy.id, name="Оргтехника")
    child = await _make_category(db_session, subsidy.id, name="Мебель", parent_id=parent.id)
    await _make_planned_item(db_session, child.id, "Стол", 1, 50_000)
    await _make_planned_item(db_session, parent.id, "Чайник электрический", 1, Decimal("1904.45"))
    await _make_planned_item(db_session, parent.id, "Термопот", 1, Decimal("6287.04"))

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    assert tree[parent.id]["display"] == pytest.approx(50_000.0 + 1904.45 + 6287.04)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]
    assert row["planned"] == pytest.approx(50_000.0 + 1904.45 + 6287.04)
    # ФЭО не введено — «Бюджет (ФЭО)» всё равно пуст, независимо от того, что
    # план посчитан правильно.
    assert row["feo_entered"] is False
    assert row["budget_basis"] is None
