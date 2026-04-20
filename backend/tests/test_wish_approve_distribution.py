"""Tests for Phase 13 Plan 02: wish approve-distribution + PATCH item scope.

Covers D-04 (drag-drop scope: item scoped to its wish), D-05 (atomic all-or-nothing
approve), D-06 (N purchases in status='wishes').

All test bodies are fully specified — no pass/... stubs.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from app import app
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.purchase import Purchase
from app.models.product import Product


async def _seed_wish_with_mixed_items(db_session, test_org, test_user):
    """Create a wish with 4 items spanning 3 resolved column keys.

    Groups:
      - Электроника (2 items: Laptop + Mouse via product.category)
      - Мебель (1 item: Chair via product.category)
      - __uncategorized__ (1 item: raw text, no product_id)
    """
    p_elec = Product(name=f"Laptop-{id(db_session)}", category="Электроника", org_id=test_org.id)
    p_furn = Product(name=f"Chair-{id(db_session)}", category="Мебель", org_id=test_org.id)
    db_session.add_all([p_elec, p_furn])
    await db_session.flush()

    w = Wish(
        org_id=test_org.id,
        title="Офис-комплект",
        status="submitted",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.flush()

    db_session.add_all([
        WishItem(
            wish_id=w.id, product_id=p_elec.id, item_name="Laptop",
            quantity=1, unit_price=50000, total_price=50000,
        ),
        WishItem(
            wish_id=w.id, product_id=p_elec.id, item_name="Mouse",
            quantity=2, unit_price=1000, total_price=2000,
        ),
        WishItem(
            wish_id=w.id, product_id=p_furn.id, item_name="Chair",
            quantity=3, unit_price=5000, total_price=15000,
        ),
        WishItem(
            wish_id=w.id, item_name="Прочее канцтовары",
            quantity=1, unit_price=100, total_price=100,
        ),  # no product_id → resolves to __uncategorized__
    ])
    await db_session.commit()
    return w


@pytest.mark.asyncio
async def test_approve_distribution_creates_n_purchases(db_session, admin_headers, test_org, test_user):
    """D-06: Happy path — POST /approve-distribution creates one purchase per column group."""
    w = await _seed_wish_with_mixed_items(db_session, test_org, test_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 3, f"expected 3 column groups, got: {body}"
    assert body["status"] == "approved"
    assert len(body["purchase_ids"]) == 3

    # Verify DB state: 3 purchases with status='wishes' committed by the endpoint
    purchases = (await db_session.execute(
        select(Purchase).where(Purchase.id.in_(body["purchase_ids"]))
    )).scalars().all()
    assert len(purchases) == 3, f"DB has {len(purchases)} purchases, expected 3"
    assert all(p.status == "wishes" for p in purchases), (
        f"Not all purchases have status='wishes': {[p.status for p in purchases]}"
    )

    # Verify wish is now approved
    await db_session.refresh(w)
    assert w.status == "approved", f"wish.status={w.status!r}, expected 'approved'"


@pytest.mark.asyncio
async def test_double_approve_returns_400(db_session, admin_headers, test_org, test_user):
    """D-05: Second approve call on already-approved wish must return 400."""
    w = await _seed_wish_with_mixed_items(db_session, test_org, test_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        first = await c.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)
        assert first.status_code == 200, f"First approve failed: {first.text}"

        second = await c.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)

    assert second.status_code == 400, second.text
    detail = second.json().get("detail", "")
    assert (
        "уже одобрена" in detail.lower()
        or "approved" in detail.lower()
    ), f"Expected 'уже одобрена' in detail, got: {detail!r}"


@pytest.mark.asyncio
async def test_patch_item_blocked_when_approved(db_session, auth_headers, admin_headers, test_org, test_user):
    """D-05: wish becomes read-only after approve. PATCH /items/{iid} returns 409 Conflict."""
    w = await _seed_wish_with_mixed_items(db_session, test_org, test_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # First approve the wish
        approve_resp = await c.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)
        assert approve_resp.status_code == 200, f"Approve failed: {approve_resp.text}"

        # Pick any item from the wish
        items = (await db_session.execute(
            select(WishItem).where(WishItem.wish_id == w.id)
        )).scalars().all()
        assert items, "Fixture should have created wish items"
        target_item = items[0]

        patch_resp = await c.patch(
            f"/api/wishes/{w.id}/items/{target_item.id}",
            json={"target_column_key": "Новая категория"},
            headers=auth_headers,
        )

    assert patch_resp.status_code == 409, patch_resp.text
    detail = patch_resp.json().get("detail", "")
    assert (
        "одобрена" in detail.lower()
        or "редактирование" in detail.lower()
    ), f"Expected locked wish message in detail, got: {detail!r}"


@pytest.mark.asyncio
async def test_patch_item_wrong_wish_returns_404(db_session, auth_headers, test_org, test_user):
    """D-04: PATCH an item using a different wish's id in the path must return 404."""
    # Wish A owns item_a
    wa = Wish(org_id=test_org.id, title="Заявка A", status="submitted", created_by=test_user.id)
    db_session.add(wa)
    await db_session.flush()
    item_a = WishItem(
        wish_id=wa.id, item_name="Item A", quantity=1, unit_price=10, total_price=10,
    )
    db_session.add(item_a)

    # Wish B — a separate wish; item_a does NOT belong here
    wb = Wish(org_id=test_org.id, title="Заявка B", status="submitted", created_by=test_user.id)
    db_session.add(wb)
    await db_session.commit()
    await db_session.refresh(item_a)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Attempt: use wish B's id in path, but item_a's id — cross-wish scope violation
        resp = await c.patch(
            f"/api/wishes/{wb.id}/items/{item_a.id}",
            json={"target_column_key": "X"},
            headers=auth_headers,
        )

    assert resp.status_code == 404, resp.text
    detail = resp.json().get("detail", "")
    assert (
        "не найдена" in detail.lower()
        or "not found" in detail.lower()
    ), f"Expected 'не найдена' in detail, got: {detail!r}"


@pytest.mark.asyncio
async def test_approve_distribution_rollback_on_failure(
    db_session, admin_headers, test_org, test_user, monkeypatch
):
    """D-05 atomicity: if Purchase creation fails on 2nd call (induced),
    ALL purchases are rolled back and wish.status remains unchanged.
    """
    w = await _seed_wish_with_mixed_items(db_session, test_org, test_user)

    # Baseline: count existing purchases associated with this wish's subsidy (None)
    before_count = await db_session.scalar(
        select(func.count()).select_from(Purchase).where(
            Purchase.subsidy_id == w.subsidy_id
        )
    ) or 0

    # Induce failure: monkeypatch Purchase.__init__ to raise on the SECOND invocation
    import app.models.purchase as purchase_module
    original_init = purchase_module.Purchase.__init__
    call_count = {"n": 0}

    def faulty_init(self, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("Induced failure for rollback test (2nd purchase)")
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(purchase_module.Purchase, "__init__", faulty_init)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)

    # Endpoint wraps exceptions → HTTP 500 with rollback message
    assert resp.status_code == 500, resp.text
    detail = resp.json().get("detail", "")
    assert (
        "откат" in detail.lower()
        or "rollback" in detail.lower()
        or "induced failure" in detail.lower()
    ), f"Expected rollback/induced-failure in detail, got: {detail!r}"

    # CRITICAL: zero new purchases must have leaked to DB
    # Expire session cache to force fresh reads from DB
    await db_session.rollback()
    after_count = await db_session.scalar(
        select(func.count()).select_from(Purchase).where(
            Purchase.subsidy_id == w.subsidy_id
        )
    ) or 0
    assert after_count == before_count, (
        f"Rollback failed: {after_count - before_count} purchases leaked into DB. "
        f"Transaction was NOT atomic. before={before_count}, after={after_count}"
    )

    # CRITICAL: wish status must NOT have changed to 'approved'
    await db_session.refresh(w)
    assert w.status == "submitted", (
        f"Wish status changed to {w.status!r} despite rollback — atomicity broken."
    )
