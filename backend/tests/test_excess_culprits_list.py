"""Задача владельца 22.10.2026, дословно: «должно подсвечивать красным
последнее добавленное, из-за чего произошёл переход через лимит плана или
ФЭО» — пример: чайник и термопот, добавленные в «Бытовую технику». Старое
find_excess_culprit называло только ОДНУ, первую пересекшую границу позицию —
фронту (FeoLevel5Panel.vue) этого было мало: владелец хочет красной ВСЮ
цепочку позиций, добавленных НАЧИНАЯ с той, что перевела категорию за лимит,
И ПОСЛЕ неё (в реальном примере — именно две последние позиции, добавленные
почти разом, вместе дали переход через ФЭО).

Эта правка добавляет "culprits" — список ВСЕХ контрибьюторов от пересекающего
границу и до конца (включительно), каждый с planned_item_id/category_id/
purchase_item_id (чтобы фронт мог найти ТОЧНУЮ строку плановой позиции или
закупки, не только категорию целиком — старая проблема: у плановой позиции
purchase_id был None, строку на фронте найти было нечем). Старые поля
(purchase_id/item_name/amount_before/amount_at_crossing/cumulative_after/
total_plan_amount/total_excess) не тронуты — их продолжают читать
test_feo_excess_culprit_matches_control.py и фронт.

Фикстуры _make_subsidy/_make_category/_make_planned_item — те же, что и в
test_feo_plan_tree_scenarios.py/test_feo_excess_culprit_matches_control.py,
второй набор фикстур не заводим.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ при диагностике: pytest tests/test_excess_culprits_list.py::<name>.
"""
from decimal import Decimal

import pytest

from app.services.feo_plan import compute_feo_plan_tree, find_excess_culprit
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


@pytest.mark.asyncio
async def test_culprits_list_includes_crossing_item_and_everything_after(db_session, test_org):
    """Статья с ФЭО 100: позиции 60 (раньше), 30, 25, 10 (позже), по порядку
    добавления. Нарастающая сумма: 60 → 90 → 115 (пересекла 100) → 125.
    culprits обязан вернуть РОВНО [25, 10] (позицию, на которой случился
    переход, и всё, что добавлено после неё), С их planned_item_id — а не
    только первую (25), как было до этой правки."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    await _make_category(db_session, subsidy.id, name="Ветка с запасом", budget=Decimal("10000000"))
    leaf = await _make_category(db_session, subsidy.id, name="Бытовая техника", budget=Decimal("100"))

    i60 = await _make_planned_item(db_session, leaf.id, "Позиция 60 (раньше всех)", 1, 60)
    i30 = await _make_planned_item(db_session, leaf.id, "Позиция 30", 1, 30)
    i25 = await _make_planned_item(db_session, leaf.id, "Чайник", 1, 25)
    i10 = await _make_planned_item(db_session, leaf.id, "Термопот", 1, 10)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == pytest.approx(125.0)
    assert node["excess_amount"] == pytest.approx(25.0)

    culprit = await find_excess_culprit(db_session, leaf.id, node["budget"])
    assert culprit is not None

    # Старые поля — поведение не изменилось (первая позиция за чертой — 25).
    assert culprit["item_name"] == "Чайник"
    assert culprit["amount_before"] == pytest.approx(90.0)
    assert culprit["amount_at_crossing"] == pytest.approx(25.0)
    assert culprit["cumulative_after"] == pytest.approx(115.0)
    assert culprit["total_plan_amount"] == pytest.approx(125.0)
    assert culprit["total_excess"] == pytest.approx(node["excess_amount"])

    # Новое поле — culprits: ровно 2 записи (Чайник, Термопот), в порядке
    # добавления, каждая со своим planned_item_id/category_id.
    culprits = culprit["culprits"]
    assert [c["item_name"] for c in culprits] == ["Чайник", "Термопот"]
    assert [c["planned_item_id"] for c in culprits] == [i25.id, i10.id]
    assert [c["amount"] for c in culprits] == [pytest.approx(25.0), pytest.approx(10.0)]
    for c in culprits:
        assert c["category_id"] == leaf.id
        assert c["purchase_id"] is None  # позиции без закупки — не связаны
        assert c["purchase_item_id"] is None

    # Позиции ДО перехода (60, 30) в culprits не попадают.
    assert i60.id not in [c["planned_item_id"] for c in culprits]
    assert i30.id not in [c["planned_item_id"] for c in culprits]


@pytest.mark.asyncio
async def test_culprits_list_single_item_matches_old_single_culprit(db_session, test_org):
    """Когда границу пересекает ЕДИНСТВЕННАЯ оставшаяся позиция (ничего не
    добавлено после неё) — culprits состоит из ОДНОЙ записи, совпадающей со
    старыми item_name/amount полями (регресс на простом случае)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    await _make_category(db_session, subsidy.id, name="Ветка с запасом", budget=Decimal("10000000"))
    leaf = await _make_category(db_session, subsidy.id, name="Категория", budget=Decimal("100"))

    await _make_planned_item(db_session, leaf.id, "Позиция 1", 1, 60)
    last = await _make_planned_item(db_session, leaf.id, "Позиция 2 (последняя)", 1, 50)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    culprit = await find_excess_culprit(db_session, leaf.id, node["budget"])
    assert culprit is not None
    assert len(culprit["culprits"]) == 1
    assert culprit["culprits"][0]["planned_item_id"] == last.id
    assert culprit["culprits"][0]["item_name"] == culprit["item_name"]
    assert culprit["culprits"][0]["amount"] == pytest.approx(culprit["amount_at_crossing"])
