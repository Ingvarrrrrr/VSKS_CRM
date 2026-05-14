"""Phase 27.1: Wave 0 — ORM model tests for ContractItem.

Tests cover:
- Creation with required fields + default match_confirmed=True
- Nullable FKs (source_item_id, product_id, contract_id)
- CASCADE delete when parent purchase is deleted
- SET NULL when source purchase_item is deleted
"""
import pytest
from decimal import Decimal
from sqlalchemy import select, delete
from app.models.contract_item import ContractItem
from app.models.purchase_item import PurchaseItem
from app.models.purchase import Purchase


@pytest.mark.asyncio
async def test_create_contract_item(db_session, make_purchase, make_contract_item):
    """ContractItem creates successfully with required fields; match_confirmed defaults True."""
    p = await make_purchase()
    ci = await make_contract_item(
        purchase_id=p.id,
        name="Тестовый товар",
        quantity=Decimal("3"),
        unit_price=Decimal("100.50"),
        total=Decimal("301.50"),
    )
    assert ci.id is not None
    assert ci.name == "Тестовый товар"
    assert ci.match_confirmed is True  # default
    assert ci.purchase_id == p.id
    assert ci.quantity == Decimal("3")
    assert ci.unit_price == Decimal("100.50")
    assert ci.total == Decimal("301.50")
    assert ci.created_at is not None


@pytest.mark.asyncio
async def test_source_item_id_nullable(db_session, make_purchase, make_contract_item):
    """All optional FKs (source_item_id, product_id, contract_id) can be NULL."""
    p = await make_purchase()
    ci = await make_contract_item(
        purchase_id=p.id,
        name="Без связи с ТЗ",
        source_item_id=None,
        product_id=None,
        contract_id=None,
    )
    assert ci.source_item_id is None
    assert ci.product_id is None
    assert ci.contract_id is None


@pytest.mark.asyncio
async def test_cascade_delete_on_purchase(db_session, make_purchase, make_contract_item):
    """Deleting a purchase cascades and removes its contract_items."""
    p = await make_purchase()
    ci = await make_contract_item(purchase_id=p.id, name="x")
    ci_id = ci.id
    await db_session.execute(delete(Purchase).where(Purchase.id == p.id))
    await db_session.commit()
    result = await db_session.execute(
        select(ContractItem).where(ContractItem.id == ci_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_set_null_on_source_item_delete(db_session, make_purchase_with_items, make_contract_item):
    """Deleting a PurchaseItem sets source_item_id to NULL (ON DELETE SET NULL)."""
    p = await make_purchase_with_items(items_count=1, status="planned")
    # Get the single purchase item
    result = await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )
    pi = result.scalar_one()
    ci = await make_contract_item(
        purchase_id=p.id, name="Linked item", source_item_id=pi.id
    )
    assert ci.source_item_id == pi.id

    # Delete the PurchaseItem
    await db_session.execute(delete(PurchaseItem).where(PurchaseItem.id == pi.id))
    await db_session.commit()

    # Refresh ContractItem — source_item_id must be NULL
    await db_session.refresh(ci)
    assert ci.source_item_id is None


@pytest.mark.asyncio
async def test_purchase_relationship_has_contract_items(db_session, make_purchase, make_contract_item):
    """Purchase.contract_items relationship works and returns ContractItem instances."""
    p = await make_purchase()
    ci1 = await make_contract_item(purchase_id=p.id, name="item 1", total=Decimal("100"))
    ci2 = await make_contract_item(purchase_id=p.id, name="item 2", total=Decimal("200"))

    await db_session.refresh(p)
    ids = {ci.id for ci in p.contract_items}
    assert ci1.id in ids
    assert ci2.id in ids
