"""Phase 27.1 D-06: CONTRACT_ITEMS_REQUIRED transition guard tests."""
import pytest
from decimal import Decimal


@pytest.mark.asyncio
async def test_contracted_requires_contract_items_422(client, make_purchase_with_items,
                                                       db_session, admin_headers):
    """Переход в contracted БЕЗ contract_items → 422 CONTRACT_ITEMS_REQUIRED."""
    p = await make_purchase_with_items(items_count=2)
    p.status = "confirmed"
    p.contract_number = "TEST-001"
    from datetime import date
    p.contract_date = date(2026, 5, 14)
    await db_session.commit()
    resp = await client.post(
        f"/api/purchases/{p.id}/transition?status=contracted", headers=admin_headers,
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "CONTRACT_ITEMS_REQUIRED"
    assert "Скопировать из заявки" in detail["message"]
    assert "Импорт из файла/QR" in detail["message"]


@pytest.mark.asyncio
async def test_contracted_with_contract_items_200(client, db_session,
                                                   make_purchase_with_items, make_contract_item,
                                                   admin_headers):
    """Переход в contracted С contract_items >= 1 → 200, contract_price пересчитан (D-07)."""
    p = await make_purchase_with_items(items_count=2)
    p.status = "confirmed"
    p.contract_number = "TEST-002"
    from datetime import date
    p.contract_date = date(2026, 5, 14)
    p.purchase_contract_type = "single"
    await db_session.commit()
    await make_contract_item(purchase_id=p.id, name="A", total=Decimal("500"))
    await make_contract_item(purchase_id=p.id, name="B", total=Decimal("300"))
    resp = await client.post(
        f"/api/purchases/{p.id}/transition?status=contracted", headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    await db_session.refresh(p)
    assert p.status == "contracted"
    # D-07 recompute: 500 + 300 = 800
    assert p.contract_price == Decimal("800")
