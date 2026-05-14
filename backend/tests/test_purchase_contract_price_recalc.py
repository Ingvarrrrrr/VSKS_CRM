"""Phase 27.1 D-07: auto-recalc contract_price = SUM(contract_items.total)."""
import pytest
from decimal import Decimal

from app.routers.purchases import _recalc_contract_price_from_contract_items


@pytest.mark.asyncio
async def test_single_contract_recalc_from_contract_items(db_session, make_purchase,
                                                            make_contract_item):
    """Разовая закупка: contract_price = SUM(contract_items.total)."""
    p = await make_purchase()
    p.purchase_contract_type = "single"
    p.purchase_method = None  # не advance
    p.parent_purchase_id = None
    p.contract_price = Decimal("0")
    await db_session.commit()
    await make_contract_item(purchase_id=p.id, name="A", total=Decimal("100"))
    await make_contract_item(purchase_id=p.id, name="B", total=Decimal("200"))
    await make_contract_item(purchase_id=p.id, name="C", total=Decimal("300"))
    await _recalc_contract_price_from_contract_items(p.id, db_session)
    await db_session.refresh(p)
    assert p.contract_price == Decimal("600")


@pytest.mark.asyncio
async def test_advance_recalc_from_contract_items(db_session, make_purchase, make_contract_item):
    """Авансовый отчёт: contract_price = SUM(contract_items.total)."""
    p = await make_purchase()
    p.purchase_contract_type = None
    p.purchase_method = "advance"
    p.parent_purchase_id = None
    p.contract_price = Decimal("0")
    await db_session.commit()
    await make_contract_item(purchase_id=p.id, name="A", total=Decimal("250"))
    await make_contract_item(purchase_id=p.id, name="B", total=Decimal("250"))
    await _recalc_contract_price_from_contract_items(p.id, db_session)
    await db_session.refresh(p)
    assert p.contract_price == Decimal("500")


@pytest.mark.asyncio
async def test_framework_child_recalc(db_session, make_purchase, make_contract_item):
    """Дочерняя рамочного (parent_purchase_id NOT NULL): contract_price = SUM (recalc applies)."""
    parent = await make_purchase()
    parent.purchase_contract_type = "framework_cumulative"
    parent.parent_purchase_id = None
    await db_session.commit()
    child = await make_purchase()
    child.purchase_contract_type = "framework_cumulative"
    child.parent_purchase_id = parent.id
    child.contract_price = Decimal("0")
    await db_session.commit()
    await make_contract_item(purchase_id=child.id, name="X", total=Decimal("777"))
    await _recalc_contract_price_from_contract_items(child.id, db_session)
    await db_session.refresh(child)
    # Child — recalc applies
    assert child.contract_price == Decimal("777")


@pytest.mark.asyncio
async def test_framework_head_manual_price(db_session, make_purchase, make_contract_item):
    """Рамочный головной (framework_cumulative, parent IS NULL): manual price НЕ перезаписывается."""
    head = await make_purchase()
    head.purchase_contract_type = "framework_cumulative"
    head.parent_purchase_id = None
    manual_price = Decimal("999999")
    head.contract_price = manual_price
    await db_session.commit()
    await make_contract_item(purchase_id=head.id, name="X", total=Decimal("1"))
    await _recalc_contract_price_from_contract_items(head.id, db_session)
    await db_session.refresh(head)
    # Head — manual_price НЕ перезаписывается
    assert head.contract_price == manual_price


@pytest.mark.asyncio
async def test_framework_limited_head_manual_price(db_session, make_purchase, make_contract_item):
    """Рамочный ограниченный головной (framework_limited, parent IS NULL): manual price НЕ перезаписывается."""
    head = await make_purchase()
    head.purchase_contract_type = "framework_limited"
    head.parent_purchase_id = None
    manual_price = Decimal("888888")
    head.contract_price = manual_price
    await db_session.commit()
    await make_contract_item(purchase_id=head.id, name="X", total=Decimal("1"))
    await _recalc_contract_price_from_contract_items(head.id, db_session)
    await db_session.refresh(head)
    assert head.contract_price == manual_price
