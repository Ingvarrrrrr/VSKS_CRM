"""Тест app.services.feo_order_diff.order_substitution_rows — задача владельца
(13.10.2026, окно «Перерасход/экономия по заказам»): строки окна строятся из
ТОЙ ЖЕ точки (committed_amounts.planned_item_order_diffs), что суммирует
compute_feo_plan_tree в order_overspend/order_economy узла — ПРАВИЛО №6,
суммы окна ОБЯЗАНЫ совпадать с подписью (Σ order_overspend/order_economy
корневых узлов дерева).

Переиспользует фабрики test_feo_plan_tree_scenarios.py/_make_linked_purchase
(test_money_committed.py) — тот же боевой пример «Форменная одежда», что и
test_feo_plan_tree_order_overspend.py::test_two_items_same_category_no_netting.
"""
import pytest

from app.services.feo_order_diff import order_substitution_rows
from app.services.feo_plan import compute_feo_plan_tree
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


@pytest.mark.asyncio
async def test_rows_match_tree_totals(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=2_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Форменная одежда", budget=2_000_000)

    fpi_suit = await _make_planned_item(db_session, leaf.id, "Повседневный костюм", 1, 586_000)
    await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi_suit.id, quantity=1, contract_price=816_900)

    fpi_hat = await _make_planned_item(db_session, leaf.id, "Шапка", 1, 106_500)
    await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi_hat.id, quantity=1, contract_price=102_900)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]

    rows = await order_substitution_rows(db_session, subsidy.id)

    # Σ строк окна == полям дерева (одна и та же точка, ПРАВИЛО №6).
    assert rows["overspend_total"] == pytest.approx(node["order_overspend"], abs=0.01)
    assert rows["economy_total"] == pytest.approx(node["order_economy"], abs=0.01)
    assert rows["overspend_total"] == pytest.approx(230_900.0, abs=0.01)
    assert rows["economy_total"] == pytest.approx(3_600.0, abs=0.01)

    assert len(rows["overspend"]) == 1
    assert rows["overspend"][0]["name"] == "Повседневный костюм"
    assert rows["overspend"][0]["plan_from_file"] == pytest.approx(586_000.0, abs=0.01)
    assert rows["overspend"][0]["contract_amount"] == pytest.approx(816_900.0, abs=0.01)
    assert rows["overspend"][0]["diff"] == pytest.approx(230_900.0, abs=0.01)
    assert rows["overspend"][0]["category_path"] == "Форменная одежда"

    assert len(rows["economy"]) == 1
    assert rows["economy"][0]["name"] == "Шапка"
    assert rows["economy"][0]["diff"] == pytest.approx(-3_600.0, abs=0.01)


@pytest.mark.asyncio
async def test_category_filter_scopes_to_subtree(db_session, test_org):
    """category_id ограничивает строки её поддеревом — другая категория той
    же субсидии не попадает в выдачу."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=2_000_000)
    leaf_a = await _make_category(db_session, subsidy.id, name="Форменная одежда", budget=1_000_000)
    leaf_b = await _make_category(db_session, subsidy.id, name="Техника", budget=1_000_000)

    fpi_a = await _make_planned_item(db_session, leaf_a.id, "Повседневный костюм", 1, 586_000)
    await _make_linked_purchase(db_session, subsidy.id, leaf_a.id, fpi_a.id, quantity=1, contract_price=816_900)

    fpi_b = await _make_planned_item(db_session, leaf_b.id, "Чайник", 1, 2_762.92)
    await _make_linked_purchase(db_session, subsidy.id, leaf_b.id, fpi_b.id, quantity=1, contract_price=17_000)

    rows_a = await order_substitution_rows(db_session, subsidy.id, category_id=leaf_a.id)
    assert len(rows_a["overspend"]) == 1
    assert rows_a["overspend"][0]["name"] == "Повседневный костюм"

    rows_all = await order_substitution_rows(db_session, subsidy.id)
    assert len(rows_all["overspend"]) == 2
    # Сортировка по модулю разницы, по убыванию.
    assert rows_all["overspend"][0]["diff"] >= rows_all["overspend"][1]["diff"]
