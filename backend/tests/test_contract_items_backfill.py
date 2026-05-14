"""Phase 27.1: idempotent backfill SQL tests.

Tests cover D-06 backfill behaviour:
- Legacy contracted purchases get 1↔1 contract_items from purchase_items
- Backfill is idempotent (NOT EXISTS guard prevents duplicates)
- contract_price is recomputed from SUM(contract_items.total) for non-framework-head purchases
- Framework head purchases keep their manual contract_price (D-07 exclusion)
- Purchases in non-contracted statuses (planned/confirmed) are NOT backfilled
"""
import pytest
from decimal import Decimal
from sqlalchemy import select, func, text
from app.models.contract_item import ContractItem
from app.models.purchase import Purchase


async def _run_backfill(db_session):
    """Helper: run backfill directly on the test DB connection."""
    from check_schema import _backfill_contract_items_from_purchase_items
    conn = await db_session.connection()
    return await _backfill_contract_items_from_purchase_items(conn)


@pytest.mark.asyncio
async def test_legacy_purchases_get_contract_items(db_session, make_legacy_contracted_purchase):
    """Contracted purchase with 2 purchase_items gets 2 contract_items after backfill."""
    p = await make_legacy_contracted_purchase(status="contracted", items_count=2, item_total=Decimal("500"))

    # Before backfill — no contract_items
    before = await db_session.execute(
        select(func.count(ContractItem.id)).where(ContractItem.purchase_id == p.id)
    )
    assert before.scalar() == 0

    await _run_backfill(db_session)

    # After — exactly 2 contract_items
    after = await db_session.execute(
        select(func.count(ContractItem.id)).where(ContractItem.purchase_id == p.id)
    )
    assert after.scalar() == 2


@pytest.mark.asyncio
async def test_backfill_idempotent(db_session, make_legacy_contracted_purchase):
    """Running backfill twice does NOT create duplicate contract_items (NOT EXISTS guard)."""
    p = await make_legacy_contracted_purchase(items_count=3)

    await _run_backfill(db_session)
    c1 = (await db_session.execute(
        select(func.count(ContractItem.id)).where(ContractItem.purchase_id == p.id)
    )).scalar()

    await _run_backfill(db_session)
    c2 = (await db_session.execute(
        select(func.count(ContractItem.id)).where(ContractItem.purchase_id == p.id)
    )).scalar()

    assert c1 == c2 == 3


@pytest.mark.asyncio
async def test_backfill_recomputes_contract_price(db_session, make_legacy_contracted_purchase):
    """After backfill, purchase.contract_price = SUM(contract_items.total) for non-framework-head."""
    p = await make_legacy_contracted_purchase(items_count=2, item_total=Decimal("750"))
    p.purchase_contract_type = "single"  # non-framework-head
    p.parent_purchase_id = None
    p.contract_price = Decimal("0")  # legacy без contract_price
    await db_session.commit()

    await _run_backfill(db_session)
    await db_session.refresh(p)

    assert p.contract_price == Decimal("1500")  # 2 × 750


@pytest.mark.asyncio
async def test_backfill_skips_framework_head(db_session, make_legacy_contracted_purchase):
    """Framework head (framework_cumulative + parent_purchase_id IS NULL) keeps its manual contract_price."""
    p = await make_legacy_contracted_purchase(items_count=2, item_total=Decimal("500"))
    p.purchase_contract_type = "framework_cumulative"
    p.parent_purchase_id = None  # головной рамочный
    manual_price = Decimal("999999")
    p.contract_price = manual_price
    await db_session.commit()

    await _run_backfill(db_session)
    await db_session.refresh(p)

    # Рамочный головной — contract_price НЕ пересчитывается
    assert p.contract_price == manual_price


@pytest.mark.asyncio
async def test_backfill_skips_non_contracted(db_session, make_purchase_with_items):
    """Purchases in planned status do NOT get contract_items from backfill."""
    p = await make_purchase_with_items(items_count=2)
    p.status = "planned"
    await db_session.commit()

    await _run_backfill(db_session)

    count = (await db_session.execute(
        select(func.count(ContractItem.id)).where(ContractItem.purchase_id == p.id)
    )).scalar()
    assert count == 0
