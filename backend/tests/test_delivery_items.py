"""Target tests for Phase 27: delivery_items."""
import pytest
from decimal import Decimal

from app.auth.jwt import create_access_token
from app.models.contract_item import ContractItem
from app.models.delivery_item import DeliveryItem
from app.models.user import User


@pytest.mark.asyncio
async def test_crud_and_server_calc_total(client, make_purchase, superadmin_headers):
    p = await make_purchase(contract_price=Decimal("1000.00"))

    # 1. Create single item: client sends total="0" or wrong total, server MUST calculate qty * unit_price
    resp = await client.post(
        f"/api/purchases/{p.id}/delivery-items",
        json={
            "name": "Ноутбук Lenovo",
            "qty": 3,
            "unit": "шт",
            "unit_price": "50000.00",
            "total": "999.00",  # wrong total from client
            "delivery_date": "2026-11-20",
            "doc_number": "УПД-101",
            "status": "pending",
        },
        headers=superadmin_headers,
    )
    assert resp.status_code == 201, resp.text
    item = resp.json()
    item_id = item["id"]
    assert item["name"] == "Ноутбук Lenovo"
    assert Decimal(str(item["qty"])) == Decimal("3")
    assert Decimal(str(item["unit_price"])) == Decimal("50000.00")
    # Server-side guaranteed total = 3 * 50000 = 150000
    assert Decimal(str(item["total"])) == Decimal("150000.00")
    assert item["status"] == "pending"
    assert item["doc_number"] == "УПД-101"
    assert item["delivery_date"] == "2026-11-20"

    # 2. List items
    list_resp = await client.get(f"/api/purchases/{p.id}/delivery-items", headers=superadmin_headers)
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == item_id
    assert "summary" in data

    # 3. Patch item: update qty and status -> total must be recalculated
    patch_resp = await client.patch(
        f"/api/purchases/{p.id}/delivery-items/{item_id}",
        json={"qty": 2, "status": "delivered"},
        headers=superadmin_headers,
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert Decimal(str(patched["qty"])) == Decimal("2")
    assert Decimal(str(patched["total"])) == Decimal("100000.00")
    assert patched["status"] == "delivered"

    # 4. Delete item
    del_resp = await client.delete(
        f"/api/purchases/{p.id}/delivery-items/{item_id}",
        headers=superadmin_headers,
    )
    assert del_resp.status_code == 204

    # Verify deleted
    list_after = await client.get(f"/api/purchases/{p.id}/delivery-items", headers=superadmin_headers)
    assert len(list_after.json()["items"]) == 0


@pytest.mark.asyncio
async def test_from_contract_and_fallback(client, db_session, make_purchase, make_purchase_with_items, superadmin_headers):
    # Test A: fallback to purchase_items when no contract_items
    p_fallback = await make_purchase_with_items(items_count=2, item_total=Decimal("250.00"))
    resp_fallback = await client.post(
        f"/api/purchases/{p_fallback.id}/delivery-items/from-contract",
        headers=superadmin_headers,
    )
    assert resp_fallback.status_code == 200, resp_fallback.text
    created = resp_fallback.json()
    assert len(created) == 2
    assert all(c["purchase_item_id"] is not None for c in created)

    # Calling again does not duplicate items
    resp_repeat = await client.post(
        f"/api/purchases/{p_fallback.id}/delivery-items/from-contract",
        headers=superadmin_headers,
    )
    assert resp_repeat.status_code == 200
    assert len(resp_repeat.json()) == 0

    # Test B: with contract_items
    p_contract = await make_purchase(contract_price=Decimal("1500.00"))
    ci1 = ContractItem(
        purchase_id=p_contract.id,
        name="Позиция по договору 1",
        quantity=Decimal("5"),
        unit="компл",
        unit_price=Decimal("200.00"),
        total=Decimal("1000.00"),
    )
    ci2 = ContractItem(
        purchase_id=p_contract.id,
        name="Позиция по договору 2",
        quantity=Decimal("1"),
        unit="шт",
        unit_price=Decimal("500.00"),
        total=Decimal("500.00"),
    )
    db_session.add_all([ci1, ci2])
    await db_session.commit()

    resp_ci = await client.post(
        f"/api/purchases/{p_contract.id}/delivery-items/from-contract",
        headers=superadmin_headers,
    )
    assert resp_ci.status_code == 200
    items_ci = resp_ci.json()
    assert len(items_ci) == 2
    assert items_ci[0]["contract_item_id"] == ci1.id
    assert Decimal(str(items_ci[0]["total"])) == Decimal("1000.00")
    assert items_ci[1]["contract_item_id"] == ci2.id
    assert Decimal(str(items_ci[1]["total"])) == Decimal("500.00")


@pytest.mark.asyncio
async def test_delivery_summary_aggregates(client, db_session, make_purchase, superadmin_headers):
    p = await make_purchase(contract_price=Decimal("1000.00"))
    ci = ContractItem(
        purchase_id=p.id,
        name="Кабель",
        quantity=Decimal("100"),
        unit="м",
        unit_price=Decimal("10.00"),
        total=Decimal("1000.00"),
    )
    db_session.add(ci)
    await db_session.commit()

    # Add 1 delivered item (50m, 500 rub) and 1 pending item (50m, 500 rub)
    d1 = DeliveryItem(
        purchase_id=p.id,
        contract_item_id=ci.id,
        name="Кабель партия 1",
        qty=Decimal("50"),
        unit_price=Decimal("10.00"),
        total=Decimal("500.00"),
        status="delivered",
    )
    d2 = DeliveryItem(
        purchase_id=p.id,
        contract_item_id=ci.id,
        name="Кабель партия 2",
        qty=Decimal("50"),
        unit_price=Decimal("10.00"),
        total=Decimal("500.00"),
        status="pending",
    )
    db_session.add_all([d1, d2])
    await db_session.commit()

    resp = await client.get(f"/api/purchases/{p.id}/delivery-items", headers=superadmin_headers)
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    assert Decimal(str(summary["contract_total"])) == Decimal("1000.00")
    assert Decimal(str(summary["delivered_total"])) == Decimal("500.00")
    assert summary["delivered_qty_pct"] == 50.0
    assert summary["delivered_amount_pct"] == 50.0
    assert summary["status_counts"]["delivered"] == 1
    assert summary["status_counts"]["pending"] == 1


@pytest.mark.asyncio
async def test_alien_user_access_returns_404(client, db_session, make_purchase):
    alien_user = User(
        username="alien_user_999",
        role="employee",
        password_hash="fakehash",
    )
    db_session.add(alien_user)
    await db_session.commit()
    await db_session.refresh(alien_user)

    alien_token = create_access_token({"sub": alien_user.username, "org_id": None})
    alien_headers = {"Authorization": f"Bearer {alien_token}"}

    # Purchase created without assignment to alien_user
    p = await make_purchase()

    # Alien user attempts access -> Rule #8 ensures 404 (hidden entity)
    resp = await client.get(f"/api/purchases/{p.id}/delivery-items", headers=alien_headers)
    assert resp.status_code == 404, resp.text

    resp_post = await client.post(
        f"/api/purchases/{p.id}/delivery-items",
        json={"name": "Hacked item", "qty": 1, "unit_price": 100},
        headers=alien_headers,
    )
    assert resp_post.status_code == 404
