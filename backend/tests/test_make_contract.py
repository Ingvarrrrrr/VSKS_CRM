"""Phase 27.1 CD-5: docxtpl contract_items context tests.

Tests verify that _build_contract_items_context returns:
  - contract_items list with correct fields
  - contract_items_total formatted string
  - contract_items_total_numeric float
  - D-08 fallback on purchase_items when contract_items empty
"""
import pytest
from decimal import Decimal


@pytest.mark.asyncio
async def test_contract_items_loop_in_template_vars(
    db_session, make_purchase, make_contract_item
):
    """CD-5: закупка с 2 contract_items — context['contract_items'] длина 2,
    каждый элемент содержит обязательные ключи."""
    from app.routers.documents import _build_contract_items_context

    p = await make_purchase()
    await make_contract_item(
        purchase_id=p.id,
        name="Товар А",
        quantity=Decimal("3"),
        unit="шт",
        unit_price=Decimal("500"),
        total=Decimal("1500"),
    )
    await make_contract_item(
        purchase_id=p.id,
        name="Товар Б",
        quantity=Decimal("1"),
        unit="комплект",
        unit_price=Decimal("2500"),
        total=Decimal("2500"),
    )

    ctx = await _build_contract_items_context(p, db_session)

    assert len(ctx["contract_items"]) == 2
    ci = ctx["contract_items"][0]
    for key in ("num", "name", "quantity", "unit", "unit_price", "total"):
        assert key in ci, f"Missing key '{key}' in contract_items[0]"
    assert ctx["contract_items"][0]["name"] == "Товар А"
    assert ctx["contract_items"][1]["name"] == "Товар Б"


@pytest.mark.asyncio
async def test_contract_items_total_formatted(
    db_session, make_purchase, make_contract_item
):
    """CD-5: contract_items_total — форматированная строка с ₽;
    contract_items_total_numeric — float; contract_item_count — int."""
    from app.routers.documents import _build_contract_items_context

    p = await make_purchase()
    await make_contract_item(purchase_id=p.id, name="X", total=Decimal("1500"))
    await make_contract_item(purchase_id=p.id, name="Y", total=Decimal("2500"))

    ctx = await _build_contract_items_context(p, db_session)

    # Numeric: 1500 + 2500 = 4000.0
    assert ctx["contract_items_total_numeric"] == 4000.0
    # Formatted string contains ruble sign
    assert "₽" in ctx["contract_items_total"]
    # And correct digits (space thousand separator)
    assert "4 000" in ctx["contract_items_total"] or "4000" in ctx["contract_items_total"]
    # Count
    assert ctx["contract_item_count"] == 2


@pytest.mark.asyncio
async def test_legacy_template_fallback_via_alias(
    db_session, make_purchase_with_items
):
    """D-08: если contract_items пустой — fallback на purchase_items.

    Закупка с 3 purchase_items БЕЗ contract_items должна дать
    context['contract_items'] длиной 3 (из purchase_items).
    """
    from app.routers.documents import _build_contract_items_context

    # purchase with 3 items, each total=100; NO contract_items
    p = await make_purchase_with_items(items_count=3, item_total=Decimal("100"))

    ctx = await _build_contract_items_context(p, db_session)

    assert len(ctx["contract_items"]) == 3, (
        f"Expected 3 items from D-08 fallback, got {len(ctx['contract_items'])}"
    )
    # Total from purchase_items: 3 × 100 = 300
    assert ctx["contract_items_total_numeric"] == 300.0
    assert ctx["contract_item_count"] == 3


@pytest.mark.asyncio
async def test_contract_items_empty_when_no_data(db_session, make_purchase):
    """Закупка без contract_items И без purchase_items — пустой список, 0."""
    from app.routers.documents import _build_contract_items_context

    p = await make_purchase()  # no purchase_items, no contract_items

    ctx = await _build_contract_items_context(p, db_session)

    assert ctx["contract_items"] == []
    assert ctx["contract_items_total_numeric"] == 0.0
    assert ctx["contract_item_count"] == 0
