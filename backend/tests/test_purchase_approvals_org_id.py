"""Regression test for the org_id mine in purchase_approvals.py.

Bug: `org_id = p.org_id or current_user.org_id` at
app/routers/purchase_approvals.py::start_approval read a column that does not
exist on Purchase (org comes from the purchase's subsidy, not its own
column) — every call to POST /api/purchases/{pid}/approvals/start crashed
with AttributeError whenever the subsidy had approvers configured. Fixed by
`_resolve_purchase_org_id()`, which resolves org via `Purchase.subsidy_id ->
Subsidy.org_id`, matching the pattern already used in purchases.py/events.py.

A second, silently-swallowed instance of the same class of bug
(`purchase.created_by_id` — a Task field, not a Purchase field) lived inside
the best-effort notification try/except in decide_approval(); fixed
alongside it.
"""
import pytest
from decimal import Decimal

from app.models.subsidy import Subsidy
from app.models.subsidy_approver import SubsidyApprover
from app.routers.purchase_approvals import _resolve_purchase_org_id


@pytest.mark.asyncio
async def test_resolve_purchase_org_id_via_subsidy(db_session, test_org, make_purchase, make_user):
    """Purchase has no org_id column — org must resolve through subsidy_id -> Subsidy.org_id."""
    subsidy = Subsidy(name="Test subsidy", year=2026, budget=1000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    p = await make_purchase(subsidy_id=subsidy.id)
    some_user = await make_user(role="employee")

    resolved = await _resolve_purchase_org_id(db_session, p, some_user)
    assert resolved == test_org.id


@pytest.mark.asyncio
async def test_resolve_purchase_org_id_fallback_to_current_user(db_session, make_purchase, test_user):
    """No subsidy on the purchase -> fall back to current_user.org_id, as before."""
    p = await make_purchase()  # subsidy_id left unset
    assert p.subsidy_id is None

    resolved = await _resolve_purchase_org_id(db_session, p, test_user)
    assert resolved == test_user.org_id


@pytest.mark.asyncio
async def test_start_approval_does_not_500(client, db_session, test_org, make_purchase, make_user):
    """Live HTTP call: starting approval on a purchase whose subsidy has approvers
    used to crash with AttributeError('Purchase' object has no attribute 'org_id').
    It must now succeed (or fail with a real business-rule 4xx), never 500."""
    subsidy = Subsidy(name="Test subsidy", year=2026, budget=1000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    approver = SubsidyApprover(
        subsidy_id=subsidy.id,
        role_name="Директор",
        full_name="Иванов И.И.",
        order_num=1,
        is_default=True,
    )
    db_session.add(approver)
    await db_session.commit()

    p = await make_purchase(subsidy_id=subsidy.id, status="work_in_progress")

    manager = await make_user(role="manager", org_id=test_org.id)
    from app.auth.jwt import create_access_token
    token = create_access_token({"sub": manager.username, "org_id": manager.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(f"/api/purchases/{p.id}/approvals/start", json={}, headers=headers)

    assert resp.status_code != 500, resp.text
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["role_name"] == "Директор"
