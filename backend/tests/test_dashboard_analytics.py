"""N1: dashboard aggregate Σ(план − договор) renamed economy -> plan_contract_delta.

Guards against re-introducing the old key name, which collided with the
unrelated manual purchase field Purchase.economy ("Экономия") — see
ПРАВИЛО №6 (один показатель — один источник истины).

ОБНОВЛЕНО 02.10.2026 (план «Деньги субсидии», шаг 3): plan_contract_delta
больше не считает Σ(planned_total_price − contract_price) закупки целиком —
это была ВТОРАЯ формула экономии (ПРАВИЛО №6). Теперь читает ЕДИНУЮ точку
(app.services.purchase_economy.purchase_economy_bulk).

ИСПРАВЛЕНО 02.10.2026 (ревью: владелец отверг базу PurchaseItem.planned_total —
на боевых данных она совпадает с ценой договора и даёт экономию 0 всегда):
база экономии строки теперь — её ПЛАНОВАЯ ПОЗИЦИЯ (FeoPlannedItem), не
planned_total. Тест обновлён — создаёт закупку с позицией, ПРИВЯЗАННОЙ к
активной FeoPlannedItem (quantity/amount), не полагается на planned_total
(который экономию больше не формирует, см. docstring purchase_economy.py).
Непривязанная позиция (feo_planned_item_id=None) теперь не измеряется вовсе
('unlinked') — см. test_6 в test_money_committed.py.
"""
import pytest
from decimal import Decimal


@pytest.mark.asyncio
async def test_analytics_returns_plan_contract_delta_not_economy(
    client, superadmin_headers, make_purchase, db_session, test_org,
):
    from app.models.purchase_item import PurchaseItem
    from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy

    # The endpoint sums over the whole (real, shared dev) database — assert
    # against the delta the new purchase adds, not an absolute total, since
    # pre-existing purchases already contribute to the sum.
    baseline_resp = await client.get("/api/dashboard/analytics", headers=superadmin_headers)
    assert baseline_resp.status_code == 200
    baseline_data = baseline_resp.json()
    assert "plan_contract_delta" in baseline_data
    assert "economy" not in baseline_data
    baseline = float(baseline_data["plan_contract_delta"])

    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="plan_contract_delta test")
    fpi = await _make_planned_item(db_session, leaf.id, "Test planned item", 1, 1000)

    purchase = await make_purchase(
        status="contracted",
        contract_price=Decimal("700"),
        subsidy_id=subsidy.id,
    )
    item = PurchaseItem(
        purchase_id=purchase.id,
        item_name="Test item",
        quantity=Decimal("1"),
        unit="шт",
        unit_price=Decimal("700"),
        total_price=Decimal("700"),
        feo_planned_item_id=fpi.id,
    )
    db_session.add(item)
    await db_session.commit()

    resp = await client.get("/api/dashboard/analytics", headers=superadmin_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "plan_contract_delta" in data
    assert "economy" not in data
    assert float(data["plan_contract_delta"]) == pytest.approx(baseline + 300.0)
