"""Регрессия 15.10.2026 — субсидия «ФАДМ 2026_3» (прод, id 100), категория
«Ремонт техники» (id 10711), плановая позиция 42925 («Ремонт автомобиля…»,
amount=0, quantity=NULL/0) с привязанной закупкой delivered на 40 730 — её
перерасход «тонул» в свободном (незаказанном) плане СОСЕДНЕЙ позиции той же
категории, «Запланировано» субсидии не менялось (ПРАВИЛО №6 нарушалось:
рядом формула plan_floor_addition по дизайну игнорирует ПРИВЯЗАННЫЕ к
FeoPlannedItem позиции, а planned_item_contributions исключала одноразовую
позицию без quantity из замещения вовсе — деньги проваливались в щель между
двумя механизмами).

Причина (committed_amounts.py, planned_item_contributions): одноразовая
(payment_mode='one_time') позиция с quantity NULL/0 никогда не входила в
_substitution_candidate_ids (фильтр `quantity > 0`) → committed-закупка по
ней не читалась вообще, contribution оставался raw_amount=0, diff=0 —
order_overspend за эту позицию не считался.

Исправление: для one_time позиций без quantity (нечем мерить «набрано
частично») любая привязанная committed-закупка (has_rows, committed_by_
planned_item) целиком замещает contribution — тот же принцип, что у позиций
с quantity, когда количество набрано полностью, просто без деления на штуки.

Боевой пример (упрощённо, те же суммы, что owner): категория с двумя
позициями — A (план 0, закупка delivered 40 730) и B (план 100 000, НЕ
заказана). budget категории 100 000. Ожидание владельца: «Запланировано»
= 140 730 (= 0+40 730 позиции A, замещённой закупкой, + 100 000 план B),
превышение над budget = 40 730.
"""
import pytest

from app.services.feo_plan import compute_feo_plan_tree
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


@pytest.mark.asyncio
async def test_item_with_zero_plan_and_no_quantity_overspend_not_netted(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=100_000)
    leaf = await _make_category(db_session, subsidy.id, name="Ремонт техники", budget=100_000)

    # Позиция A: план 0, БЕЗ quantity (как 42925 на проде) — закупка delivered
    # на 40 730, привязанная (feo_planned_item_id), не over_plan.
    fpi_a = await _make_planned_item(db_session, leaf.id, "Ремонт автомобиля", 0, 0)
    await _make_linked_purchase(
        db_session, subsidy.id, leaf.id, fpi_a.id,
        quantity=1, contract_price=40_730, status="delivered",
    )

    # Позиция B: план 100 000, НЕ заказана — её свободный план раньше "гасил"
    # перерасход A внутри категории (committed_by_category агрегирован).
    await _make_planned_item(db_session, leaf.id, "Запчасти", 1, 100_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]

    assert node["plan_items_raw"] == pytest.approx(100_000.0, abs=0.01)  # 0 (A) + 100 000 (B)
    assert node["order_overspend"] == pytest.approx(40_730.0, abs=0.01)
    assert node["order_economy"] == 0.0
    assert node["plan_manual"] == pytest.approx(140_730.0, abs=0.01)  # «Запланировано» узла
    assert node["excess_amount"] == pytest.approx(40_730.0, abs=0.01)  # превышение над budget 100 000

    # Инвариант c905c962: plan_items_raw + order_overspend − order_economy == plan_manual
    assert abs(
        (node["plan_items_raw"] + node["order_overspend"] - node["order_economy"]) - node["plan_manual"]
    ) < 0.01
