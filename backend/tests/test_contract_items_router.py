"""Phase 27.1 D-01: CRUD + copy-from-purchase integration tests."""
import pytest
from decimal import Decimal
from sqlalchemy import select

from app.models.contract_item import ContractItem


@pytest.mark.asyncio
async def test_create_contract_item(client, make_purchase, admin_headers):
    p = await make_purchase()
    resp = await client.post(
        f"/api/purchases/{p.id}/contract-items",
        json={"name": "Товар А", "quantity": 5, "unit": "шт",
              "unit_price": "100.50", "total": "502.50"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Товар А"
    assert body["purchase_id"] == p.id


@pytest.mark.asyncio
async def test_list_contract_items(client, make_purchase, make_contract_item, admin_headers):
    p = await make_purchase()
    await make_contract_item(purchase_id=p.id, name="X")
    await make_contract_item(purchase_id=p.id, name="Y")
    resp = await client.get(f"/api/purchases/{p.id}/contract-items", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_patch_contract_item(client, make_purchase, make_contract_item, admin_headers):
    p = await make_purchase()
    ci = await make_contract_item(purchase_id=p.id, name="Old", total=Decimal("100"))
    resp = await client.patch(
        f"/api/purchases/{p.id}/contract-items/{ci.id}",
        json={"name": "New", "total": "200"}, headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


@pytest.mark.asyncio
async def test_delete_contract_item(client, make_purchase, make_contract_item, admin_headers):
    p = await make_purchase()
    ci = await make_contract_item(purchase_id=p.id, name="x")
    resp = await client.delete(
        f"/api/purchases/{p.id}/contract-items/{ci.id}", headers=admin_headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_copy_from_purchase_items(client, db_session,
                                         make_purchase_with_items, admin_headers):
    p = await make_purchase_with_items(items_count=3, item_total=Decimal("250"))
    resp = await client.post(
        f"/api/purchases/{p.id}/contract-items/copy-from-purchase",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    assert all(c["source_item_id"] is not None for c in body)


@pytest.mark.asyncio
async def test_copy_from_purchase_empty_items_422(client, make_purchase, admin_headers):
    p = await make_purchase()  # без purchase_items
    resp = await client.post(
        f"/api/purchases/{p.id}/contract-items/copy-from-purchase",
        headers=admin_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "NO_PURCHASE_ITEMS"


@pytest.mark.asyncio
async def test_replace_all_atomic(client, db_session, make_purchase,
                                   make_contract_item, admin_headers):
    p = await make_purchase()
    await make_contract_item(purchase_id=p.id, name="Old1")
    await make_contract_item(purchase_id=p.id, name="Old2")
    resp = await client.put(
        f"/api/purchases/{p.id}/contract-items",
        json=[{"name": "New1", "total": "100"}, {"name": "New2", "total": "200"}],
        headers=admin_headers,
    )
    assert resp.status_code == 200
    result = await db_session.execute(
        select(ContractItem).where(ContractItem.purchase_id == p.id)
    )
    names = [ci.name for ci in result.scalars().all()]
    assert set(names) == {"New1", "New2"}


@pytest.mark.asyncio
async def test_router_resolves_before_purchases_catch_all(client, make_purchase, admin_headers):
    """Catch-all guard test: /contract-items НЕ должен матчиться с /{purchase_id} в purchases.router."""
    p = await make_purchase()
    # GET /api/purchases/{pid}/contract-items должен попасть в contract_items router (200),
    # а НЕ в purchases.get_purchase (которая попыталась бы парсить pid="N/contract-items")
    resp = await client.get(
        f"/api/purchases/{p.id}/contract-items", headers=admin_headers,
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
