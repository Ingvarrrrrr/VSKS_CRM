"""N1: dashboard aggregate Σ(план − договор) renamed economy -> plan_contract_delta.

Guards against re-introducing the old key name, which collided with the
unrelated manual purchase field Purchase.economy ("Экономия") — see
ПРАВИЛО №6 (один показатель — один источник истины).
"""
import pytest
from decimal import Decimal


@pytest.mark.asyncio
async def test_analytics_returns_plan_contract_delta_not_economy(
    client, superadmin_headers, make_purchase
):
    # The endpoint sums over the whole (real, shared dev) database — assert
    # against the delta the new purchase adds, not an absolute total, since
    # pre-existing purchases already contribute to the sum.
    baseline_resp = await client.get("/api/dashboard/analytics", headers=superadmin_headers)
    assert baseline_resp.status_code == 200
    baseline_data = baseline_resp.json()
    assert "plan_contract_delta" in baseline_data
    assert "economy" not in baseline_data
    baseline = float(baseline_data["plan_contract_delta"])

    await make_purchase(
        status="contracted",
        planned_total_price=Decimal("1000"),
        contract_price=Decimal("700"),
    )

    resp = await client.get("/api/dashboard/analytics", headers=superadmin_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "plan_contract_delta" in data
    assert "economy" not in data
    assert float(data["plan_contract_delta"]) == pytest.approx(baseline + 300.0)
