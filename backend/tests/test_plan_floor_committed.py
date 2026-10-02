"""Шаг 3 плана «Деньги субсидии» (владелец, решение 02.10.2026, «договор входит
в план» — .planning/quick/2026-10-02-money-redistribution/PLAN.md).

Повод: на проде есть договоры в категориях БЕЗ плановых позиций (или с планом
меньше факта договора) — МИНПРОС_2026 («Услуги по изготовлению брендированного
комбинезона…», 0 плановых позиций, договор РЕЕ-2026-00850 на 1 935 000 ₽),
ФАДМ_2026 (1 358 685 ₽ в трёх категориях). Эти деньги не попадали в
«Запланировано» — «Свободно» считало их свободными, хотя они заняты, и
получалось «Свободно» > «Можно перераспределить», чего быть не должно.

Правило (plan_floor_addition, app.services.feo_plan_common, ПРАВИЛО №6 —
ЕДИНАЯ точка и для compute_feo_plan_tree, и для find_excess_culprit): на
СОБСТВЕННОЙ части каждого узла display (own plan + own over) не может быть
меньше законтрактованного этой же собственной части (committed, ТОЛЬКО
НЕпривязанные позиции, но включая over_plan — см. докстринг функции о том,
почему не node['committed'] целиком). Добавка публикуется отдельно
(node['plan_floor_added']).

Фабрики (_make_subsidy/_make_category/_make_planned_item) — из
test_feo_plan_tree_scenarios.py; _make_unlinked_purchase — из
test_money_committed.py (ПРАВИЛО №6, вторая копия не заводится).
"""
from decimal import Decimal

import pytest

from app.services.feo_plan import assert_no_unapproved_excess, compute_feo_plan_tree, find_excess_culprit
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_unlinked_purchase


@pytest.mark.asyncio
async def test_1_contract_without_plan_item_raises_floor(client, superadmin_headers, db_session, test_org):
    """Категория БЕЗ плановых позиций, бюджет 1 950 000, договор (contracted)
    1 935 000 → display 1 935 000, plan_floor_added 1 935 000,
    planned_not_committed 0, redistributable узла = 15 000; на уровне субсидии
    инвариант remaining + planned_not_committed == redistributable держится и
    remaining <= redistributable (деньги договора больше не считаются
    свободными)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_950_000)
    leaf = await _make_category(
        db_session, subsidy.id, name="Услуги по изготовлению брендированного комбинезона",
        budget=Decimal("1950000"),
    )
    await _make_unlinked_purchase(db_session, subsidy.id, leaf.id, quantity=1, contract_price=1_935_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["committed"] == pytest.approx(1_935_000.0)
    assert node["plan_floor_added"] == pytest.approx(1_935_000.0)
    assert node["plan"] == pytest.approx(1_935_000.0)
    assert node["display"] == pytest.approx(1_935_000.0)
    assert node["excess_amount"] == 0.0, "бюджет (1 950 000) покрывает договор — превышения нет"
    assert node["planned_not_committed"] == pytest.approx(0.0)
    assert node["redistributable"] == pytest.approx(15_000.0)
    # Типовой split не должен разойтись со scalar'ом (test_feo_plan_tree_type_split.py).
    assert (node["plan_goods"] + node["plan_services"] + node["plan_unspecified"]) == pytest.approx(node["display"])

    resp = await client.get("/api/dashboard/charts", headers=superadmin_headers)
    assert resp.status_code == 200
    stats = {s["id"]: s for s in resp.json()["subsidy_stats"]}
    row = stats[subsidy.id]
    assert row["remaining"] + row["planned_not_committed"] == pytest.approx(row["redistributable"])
    assert row["remaining"] <= row["redistributable"] + 0.01


@pytest.mark.asyncio
async def test_2_plan_already_covers_unlinked_contract_no_floor(db_session, test_org):
    """Категория с плановыми позициями (2 584 000, количество НЕ набрано
    договором) и непривязанным договором 332 000 — план уже резервирует
    больше, чем реально законтрактовано → пола нет (plan_floor_added 0),
    display остаётся 2 584 000."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=5_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="План покрывает договор", budget=Decimal("5000000"))
    await _make_planned_item(db_session, leaf.id, "Позиция плана", 100, 2_584_000)

    await _make_unlinked_purchase(db_session, subsidy.id, leaf.id, quantity=1, contract_price=332_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_floor_added"] == 0.0
    assert node["plan"] == pytest.approx(2_584_000.0)
    assert node["display"] == pytest.approx(2_584_000.0)


@pytest.mark.asyncio
async def test_3_framework_head_contracted_not_committed_no_floor(db_session, test_org):
    """Рамочный договор в статусе «Договор» (contracted, НЕ «Заказано») в
    категории без плана — сама рамочная голова ещё НЕ законтрактована
    (committed_status_predicate требует ordered+ для рамочных) → пола нет."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Рамочный без плана", budget=Decimal("1000000"))

    await _make_unlinked_purchase(
        db_session, subsidy.id, leaf.id, quantity=1, contract_price=600_000,
        status="contracted", purchase_contract_type="framework_cumulative",
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["committed"] == 0.0, "рамочная голова на этапе «Договор» денег не занимает"
    assert node["plan_floor_added"] == 0.0
    assert node["plan"] == 0.0
    assert node["display"] == 0.0


@pytest.mark.asyncio
async def test_4_group_rollup_sums_children_floor(db_session, test_org):
    """Группа из двух листьев — один с полом (договор без плана), другой без
    (план уже покрывает договор) — group.plan_floor_added == Σ детей, и
    group.plan/display == Σ детей (обычный rollup, без собственных позиций
    группы), типовой split сходится и у листьев, и у группы."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=10_000_000)
    group = await _make_category(db_session, subsidy.id, name="Направление")
    leaf_floor = await _make_category(db_session, subsidy.id, parent_id=group.id, name="Без плана, с договором")
    leaf_plain = await _make_category(db_session, subsidy.id, parent_id=group.id, name="С планом, без пола")

    await _make_unlinked_purchase(db_session, subsidy.id, leaf_floor.id, quantity=1, contract_price=500_000)
    await _make_planned_item(db_session, leaf_plain.id, "Позиция плана", 10, 700_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_floor = tree[leaf_floor.id]
    node_plain = tree[leaf_plain.id]
    node_group = tree[group.id]

    assert node_floor["plan_floor_added"] == pytest.approx(500_000.0)
    assert node_plain["plan_floor_added"] == 0.0
    assert node_group["plan_floor_added"] == pytest.approx(500_000.0)
    assert node_group["plan"] == pytest.approx(node_floor["plan"] + node_plain["plan"])
    assert node_group["display"] == pytest.approx(node_floor["display"] + node_plain["display"])

    for node in (node_floor, node_plain, node_group):
        assert (node["plan_goods"] + node["plan_services"] + node["plan_unspecified"]) == pytest.approx(
            node["display"]
        )


@pytest.mark.asyncio
async def test_5_contract_over_budget_still_triggers_excess_control(db_session, test_org):
    """Договор (2 100 000) дороже бюджета категории без плана (2 000 000) —
    display поднимается полом, но контроль «план над ФЭО» по-прежнему
    срабатывает (не обойдён полом): excess_amount > 0, assert_no_unapproved_
    excess возвращает предупреждение, и find_excess_culprit называет ТО ЖЕ
    итоговое превышение, что и node['excess_amount'] (ПРАВИЛО №6 — дерево и
    контроль читают одну добавку)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=5_000_000)
    # Второй корневой узел с запасом — суммарный потолок субсидии не должен
    # перекрыть узловую проверку раньше, чем мы до неё доберёмся (приём из
    # test_feo_excess_culprit_matches_control.py).
    await _make_category(db_session, subsidy.id, name="Ветка с запасом", budget=Decimal("3000000"))
    leaf = await _make_category(db_session, subsidy.id, name="Договор дороже бюджета", budget=Decimal("2000000"))

    await _make_unlinked_purchase(db_session, subsidy.id, leaf.id, quantity=1, contract_price=2_100_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["committed"] == pytest.approx(2_100_000.0)
    assert node["plan_floor_added"] == pytest.approx(2_100_000.0)
    assert node["excess_amount"] == pytest.approx(100_000.0), "план (поднятый полом) дороже бюджета на 100 000"

    warnings = await assert_no_unapproved_excess(db_session, leaf.id)
    codes = [w["code"] for w in warnings]
    assert "PLAN_EXCESS_OVER_FEO" in codes, "контроль «план над ФЭО» не должен теряться из-за пола"

    culprit = await find_excess_culprit(db_session, leaf.id, node["budget"])
    assert culprit is not None
    assert culprit["total_excess"] == pytest.approx(node["excess_amount"]), (
        "справка о виновнике обязана называть ТО ЖЕ превышение, что и плашка — "
        "включая добавку пола, а не только Σ плановых позиций"
    )
    assert culprit["total_plan_amount"] == pytest.approx(node["plan"] + node["over"])
