"""Задача владельца (22.10.2026, прод ДНР_2026 id 104) — кнопка «Приравнять
ФЭО к плану» (app.services.feo_tree_write.align_budget_to_plan/_all) пишет
FeoCategory.budget := node["plan"] + node["over"] — план статьи С УЧЁТОМ
ДОГОВОРОВ (позиция, закрытая договором по количеству, считается по сумме
договора, см. committed_amounts.leaf_items_committed_contribution). Разбивка
ФЭО по типам (товары/услуги/ФОТ/без типа, feo_plan_tree.py::_feo_by_kind)
решала «ФЭО приравнено к плану?» ТОЛЬКО через голую Σ amount плановых позиций
(_plan_items_pool_by_kind) — без договоров. Если позиция закрыта договором на
сумму, отличную от amount, budget (= план с договором) не совпадал с этим
пулом → ВСЁ ФЭО статьи уходило в «без типа» (боевой замер: три статьи ДНР_2026,
Σ позиций меньше budget на 12 892 / 16 400 / 224 848 → ФЭО товаров занижено
на 8 105 486,69, ложное «превышение плана над ФЭО по товарам»).

Фикс — item_type_split.pick_aligned_pool + feo_plan_tree._plan_with_contracts_
pool_by_kind: «приравнено» теперь проверяется И по голой Σ позиций (старое
поведение, сценарий (b)), И по плану С УЧЁТОМ договоров (новый кандидат,
сценарий (a)); не совпало ни с одним — budget это своя сумма владельца
(правило 14.10.2026, сценарий (c), НЕ сломано).

Фабрики: _make_subsidy/_make_category/_make_planned_item (с item_type) — из
test_feo_plan_tree_type_split.py; _make_linked_purchase (закупка, привязанная
к плановой позиции, закрывающая её по количеству) — из test_money_committed.py
(ПРАВИЛО №6 — вторая копия фабрик не заводится).

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять
КАЖДЫЙ тест ПО ОТДЕЛЬНОСТИ.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import feo_tree_write
from app.services.feo_plan_tree import compute_feo_plan_tree, compute_subsidy_type_summary
from tests.test_feo_plan_tree_type_split import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


def _mk_admin_user(org_id):
    return SimpleNamespace(role="org_admin", id=1, org_id=org_id, _active_org_id=org_id, _uoa_org_ids=[])


async def _build_scenario(db_session, test_org):
    """Статья с ОДНОЙ плановой позицией (товар, qty=1, amount=100), закрытой
    ДОГОВОРОМ на 120 (quantity=1 >= plan qty=1 -> «законтрактовано целиком»
    замещает план, см. feo_plan_tree._own_plan_floor/_manual_plan_for) — план
    статьи С УЧЁТОМ договора = 120, голая Σ позиций = 100."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья — товар закрыт договором дороже плана")
    fpi = await _make_planned_item(db_session, cat.id, "Товар (план)", 100, item_type="товар", quantity=1)
    await _make_linked_purchase(
        db_session, subsidy.id, cat.id, fpi.id, quantity=1, contract_price=120,
    )
    return subsidy, cat, fpi


@pytest.mark.asyncio
async def test_a_aligned_with_contracts_pool_splits_by_type(db_session, test_org):
    """(a) budget := node['plan']+node['over'] через реальную кнопку
    (feo_tree_write.align_budget_to_plan) -> 120 (план С УЧЁТОМ договора, не
    голая Σ позиций 100) -> приравнено к НОВОМУ пулу-с-договорами ->
    feo_goods==120 (не 0/«без типа»), excess plan_over_feo_goods == 0."""
    subsidy, cat, fpi = await _build_scenario(db_session, test_org)

    tree_before = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_before = tree_before[cat.id]
    assert node_before["plan"] == pytest.approx(120.0), "план замещён законтрактованной суммой (договор дороже плана)"
    assert node_before["over"] == pytest.approx(0.0)

    user = _mk_admin_user(test_org.id)
    await feo_tree_write.align_budget_to_plan(db_session, user, cat)
    await db_session.commit()
    await db_session.refresh(cat)
    assert float(cat.budget) == pytest.approx(120.0)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["feo_goods"] == pytest.approx(120.0), "ФЭО приравнено к плану-с-договором -> делится по его типу"
    assert node["feo_unspecified"] == pytest.approx(0.0)
    info = node["feo_split_explicit"]
    assert info is not None and info.get("aligned") is True

    summary = await compute_subsidy_type_summary(db_session, subsidy.id, tree)
    assert summary["excess"]["plan_over_feo_goods"]["amount"] == pytest.approx(0.0), (
        "боевой симптом ДНР_2026: ложное превышение плана над ФЭО по товарам обязано исчезнуть"
    )


@pytest.mark.asyncio
async def test_b_budget_equal_to_raw_items_sum_still_splits_old_way(db_session, test_org):
    """(b) budget == Σ голых плановых позиций (100, старое поведение ДО
    фикса) -> приравнено к items_pool (ПЕРВЫЙ кандидат, поведение НЕ
    изменилось) -> feo_goods==100."""
    subsidy, cat, fpi = await _build_scenario(db_session, test_org)
    cat.budget = Decimal("100")
    await db_session.commit()

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["feo_goods"] == pytest.approx(100.0)
    assert node["feo_unspecified"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_c_own_amount_not_matching_any_pool_stays_unspecified(db_session, test_org):
    """(c) Правило владельца 14.10.2026 НЕ сломано: budget == 130 — своя
    сумма, не совпадающая ни с items_pool (100), ни с planned-with-contracts
    pool (120) -> весь budget в «без типа», feo_goods == 0."""
    subsidy, cat, fpi = await _build_scenario(db_session, test_org)
    cat.budget = Decimal("130")
    await db_session.commit()

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["feo_goods"] == pytest.approx(0.0)
    assert node["feo_unspecified"] == pytest.approx(130.0)
    assert node["feo_split_explicit"] is None
