"""Тест новых полей дерева order_overspend/order_economy (compute_feo_plan_tree,
feo_plan_tree.py) — задача владельца 13.10.2026, «перерасход по заказам»
рядом с уже существующей «экономией по заказам» (plan_items_raw, правка
12.10.2026). ЖЁСТКОЕ ОГРАНИЧЕНИЕ задачи: plan/plan_manual/display/excess_* не
меняются ни на копейку — эти поля только РАСКЛАДЫВАЮТ уже посчитанную разницу
plan_items_raw ↔ plan_manual на две неотрицательные стороны.

Переиспользует фабрики _make_subsidy/_make_category/_make_planned_item
(test_feo_plan_tree_scenarios.py) и _make_linked_purchase (test_money_committed.py)
— ПРАВИЛО №6, вторая копия не заводится.
"""
import pytest

from app.services.feo_plan import compute_feo_plan_tree
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


def _assert_identity(node):
    """plan_items_raw + order_overspend − order_economy == plan_manual —
    инвариант, держащийся на КАЖДОМ узле дерева (см. docstring функции)."""
    assert abs(
        (node["plan_items_raw"] + node["order_overspend"] - node["order_economy"]) - node["plan_manual"]
    ) < 0.01


@pytest.mark.asyncio
async def test_owner_suit_example_overspend_230900(db_session, test_org):
    """Боевой пример владельца: план позиции «Повседневный костюм» 586 000,00,
    заказ/договор одной строкой, полностью набравший количество, на
    816 900,00 — order_overspend 230 900, order_economy 0, plan_manual =
    816 900 (как и раньше, display/excess_* не затронуты этой задачей)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Повседневный костюм (лист)", budget=1_000_000)
    fpi = await _make_planned_item(db_session, leaf.id, "Повседневный костюм", 1, 586_000)

    await _make_linked_purchase(
        db_session, subsidy.id, leaf.id, fpi.id, quantity=1, contract_price=816_900,
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]

    assert node["plan_items_raw"] == 586_000.0
    assert node["plan_manual"] == 816_900.0  # НЕ изменилось этой задачей
    assert node["order_overspend"] == pytest.approx(230_900.0, abs=0.01)
    assert node["order_economy"] == 0.0
    _assert_identity(node)


@pytest.mark.asyncio
async def test_owner_example_economy_still_zero_overspend(db_session, test_org):
    """Зеркальный пример («Haval» — заказ ДЕШЕВЛЕ плана): order_economy > 0,
    order_overspend == 0 — обе стороны инварианта независимо проверены."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Haval Dargo (лист)", budget=1_000_000)
    fpi = await _make_planned_item(db_session, leaf.id, "Haval Dargo Р937ХУ 180", 1, 25_000)

    await _make_linked_purchase(
        db_session, subsidy.id, leaf.id, fpi.id, quantity=1, contract_price=8_826.23,
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]

    assert node["plan_items_raw"] == 25_000.0
    assert node["plan_manual"] == pytest.approx(8_826.23, abs=0.01)
    assert node["order_overspend"] == 0.0
    assert node["order_economy"] == pytest.approx(16_173.77, abs=0.01)
    _assert_identity(node)


@pytest.mark.asyncio
async def test_rollup_to_group_node(db_session, test_org):
    """Группа (узел с детьми) — order_overspend/order_economy это Σ по
    поддереву (own + rollup детей), та же схема, что и у plan_items_raw/
    plan_manual (см. ветку группы в _visit)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=2_000_000)
    group = await _make_category(db_session, subsidy.id, name="Форма (направление)")
    leaf_over = await _make_category(db_session, subsidy.id, parent_id=group.id, name="Костюм", budget=1_000_000)
    leaf_econ = await _make_category(db_session, subsidy.id, parent_id=group.id, name="Haval", budget=1_000_000)

    fpi_over = await _make_planned_item(db_session, leaf_over.id, "Костюм", 1, 586_000)
    await _make_linked_purchase(db_session, subsidy.id, leaf_over.id, fpi_over.id, quantity=1, contract_price=816_900)

    fpi_econ = await _make_planned_item(db_session, leaf_econ.id, "Haval", 1, 25_000)
    await _make_linked_purchase(db_session, subsidy.id, leaf_econ.id, fpi_econ.id, quantity=1, contract_price=8_826.23)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    group_node = tree[group.id]

    assert group_node["order_overspend"] == pytest.approx(230_900.0, abs=0.01)
    assert group_node["order_economy"] == pytest.approx(16_173.77, abs=0.01)
    _assert_identity(group_node)
    _assert_identity(tree[leaf_over.id])
    _assert_identity(tree[leaf_econ.id])
