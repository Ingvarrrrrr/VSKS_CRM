"""Владелец, Волна 1 п.8/п.7 (2026-09-13), дословно (п.8): «Когда в поле
финансирование по ФЭО введено „0“, то в моём понимании это значит, что не
задана сумма. Если алгоритм считает, что любая сумма в плановых отображается
как превышение — это неправильно. Ведь если нет жёстко заданной суммы, то и
сравнивать не с чем.»

(п.7, боевой сценарий): «У „Канцтоваров для Курского штаба“ по ФЭО ничего не
закладывалось, но требуется согласовать превышение. Раз у самой позиции сумма
по ФЭО не задана — по этому уровню согласовывать не надо. Раз плановое
значение категории „Канцелярские и бытовые расходы“ (481 972) не превышает
значение по ФЭО этой же категории — тут тоже согласовывать нечего.»

Фикс — app.services.feo_plan_tree.compute_feo_plan_tree._visit: budget=0.0
теперь нормализуется до None ДО сравнения с планом (см. `_raw_budget in
(None, 0.0)`), наравне с уже поддерживаемым NULL. Контроль ПРОДОЛЖАЕТ
подниматься выше по дереву — родитель со своим заданным (ненулевым) budget
проверяется как раньше (см. test_d_* ниже, узел-предок).

Узлы (по заданию, буквы владельца):
  (а) budget=0 у категории с планом сверху → excess_amount=0.0, budget в
      узле нормализован до None, assert_no_unapproved_excess не поднимает
      предупреждений/409.
  (б) budget=NULL (не задан вообще) → тот же результат — регрессия против
      уже существовавшего поведения (baseline ДО этой задачи).
  (в) budget задан и НЕНУЛЕВОЙ, план выше него → excess_amount поднимается
      КАК РАНЬШЕ (регрессия — фикс не должен был тронуть этот путь). Вторая
      ветка с запасом добавлена, чтобы суммарный потолок субсидии
      (PLAN_OVER_SUBSIDY_CEILING) не перекрыл узловую проверку — тот же
      приём, что и test_a_branch_over_budget_alone_does_not_block_within_ceiling
      в test_excess_total_not_per_branch.py.
  (г) боевой сценарий владельца целиком: лист без суммы ФЭО (budget=0)
      внутри категории с заданной суммой (481 972), план категории (плюс
      план листа) НЕ превышает — согласование не требуется НИ на одном
      уровне (ни на листе, ни на категории-предке).

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ: pytest tests/test_feo_zero_budget_means_unset.py::<name>.
"""
import uuid
from decimal import Decimal

import pytest

from app.services.feo_plan import assert_no_unapproved_excess, compute_feo_plan_tree


async def _make_subsidy(db_session, org_id, budget=1_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"ZeroBudget-Subsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, parent_id=None, **kwargs):
    from app.models.feo_category import FeoCategory
    level = 1 if parent_id is None else 2
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=parent_id,
        level=level,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, amount, quantity=1, name="Позиция плана", is_active=True):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=name,
        quantity=Decimal(str(quantity)),
        unit="шт",
        amount=Decimal(str(amount)),
        is_active=is_active,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


@pytest.mark.asyncio
async def test_a_zero_budget_means_unset_no_excess(db_session, test_org):
    """(а) budget=0 (явный ноль, как после Excel-импорта в пустую ячейку) —
    план 150 000 поверх НЕ считается превышением: сравнивать не с чем."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    cat = await _make_category(
        db_session, subsidy.id, name="Ветка — budget=0", budget=Decimal("0"),
    )
    await _make_planned_item(db_session, cat.id, amount=150_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["plan_manual"] == 150_000.0
    assert node["budget"] is None, "budget=0 обязан нормализоваться до None"
    assert node["excess_amount"] == 0.0
    assert node["excess_pending"] is False
    assert node["display"] == 150_000.0, "без заданного budget план не откатывается — display = полный план"

    warnings = await assert_no_unapproved_excess(db_session, cat.id)
    assert warnings == [], "budget=0 не должен поднимать предупреждение о превышении"


@pytest.mark.asyncio
async def test_b_null_budget_means_unset_no_excess(db_session, test_org):
    """(б) budget вообще не задан (NULL) — тот же результат, что и (а)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    cat = await _make_category(
        db_session, subsidy.id, name="Ветка — budget=NULL",
    )
    await _make_planned_item(db_session, cat.id, amount=150_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["plan_manual"] == 150_000.0
    assert node["budget"] is None
    assert node["excess_amount"] == 0.0

    warnings = await assert_no_unapproved_excess(db_session, cat.id)
    assert warnings == []


@pytest.mark.asyncio
async def test_c_nonzero_budget_still_flags_excess(db_session, test_org):
    """(в) регрессия — budget ЗАДАН и ненулевой: превышение поднимается КАК
    РАНЬШЕ. Ветка B с запасом добавлена, чтобы суммарный потолок субсидии не
    перекрыл узловую PLAN_EXCESS_OVER_FEO проверку раньше, чем она сработает
    (тот же приём, что в test_excess_total_not_per_branch.py)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = await _make_category(db_session, subsidy.id, name="Ветка A (перебор)", budget=Decimal("100000"))
    cat_b = await _make_category(db_session, subsidy.id, name="Ветка B (запас)", budget=Decimal("100000"))
    await _make_planned_item(db_session, cat_a.id, amount=150_000)
    await _make_planned_item(db_session, cat_b.id, amount=50_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_a = tree[cat_a.id]
    assert node_a["budget"] == 100_000.0
    assert node_a["excess_amount"] == pytest.approx(50_000.0)
    assert node_a["display"] == pytest.approx(150_000.0), "без согласования план не входит в display"

    warnings = await assert_no_unapproved_excess(db_session, cat_a.id)
    assert warnings, "ненулевой budget с превышением обязан вернуть предупреждение — фикс не должен был это сломать"
    assert warnings[0]["code"] == "PLAN_EXCESS_OVER_FEO"
    assert warnings[0]["excess_amount"] == pytest.approx(50_000.0)


@pytest.mark.asyncio
async def test_d_owner_scenario_kursk_office_supplies(db_session, test_org):
    """(г) Боевой сценарий владельца целиком: лист «Канцтовары для Курского
    штаба» без суммы по ФЭО (budget=0) внутри категории «Канцелярские и
    бытовые расходы» (budget=481 972 — реальное число из жалобы владельца).
    План листа (50 000) поднимается в план категории, который НЕ превышает
    481 972 → согласование не требуется НИ на листе, НИ на категории."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    category = await _make_category(
        db_session, subsidy.id,
        name="Канцелярские и бытовые расходы",
        budget=Decimal("481972"),
    )
    leaf = await _make_category(
        db_session, subsidy.id, parent_id=category.id,
        name="Канцтовары для Курского штаба",
        budget=Decimal("0"),
    )
    await _make_planned_item(db_session, leaf.id, amount=50_000, name="Канцтовары для Курского штаба")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])

    leaf_node = tree[leaf.id]
    assert leaf_node["budget"] is None, "budget=0 листа обязан нормализоваться до None"
    assert leaf_node["excess_amount"] == 0.0
    assert leaf_node["plan_manual"] == 50_000.0

    cat_node = tree[category.id]
    assert cat_node["budget"] == 481_972.0
    assert cat_node["plan"] == pytest.approx(50_000.0), "план листа обязан подняться в план категории-предка"
    assert cat_node["display"] == pytest.approx(50_000.0)
    assert cat_node["excess_amount"] == 0.0, "план категории (50 000) не превышает её budget (481 972)"

    warnings_leaf = await assert_no_unapproved_excess(db_session, leaf.id)
    assert warnings_leaf == [], "лист без суммы ФЭО не должен требовать согласования"

    warnings_cat = await assert_no_unapproved_excess(db_session, category.id)
    assert warnings_cat == [], "план категории в пределах её ФЭО — согласовывать нечего"
