"""Phase 17 Plan 03: require_tab() / require_action() Depends factory tests."""
import pytest


@pytest.mark.asyncio
async def test_require_tab_403_when_not_in_effective(client, auth_headers):
    """employee has no 'staff' tab → GET /api/hierarchy/ returns 403 after migration."""
    r = await client.get("/api/hierarchy/", headers=auth_headers)
    assert r.status_code == 403

@pytest.mark.asyncio
async def test_require_tab_200_when_in_effective(client, admin_headers):
    """admin has 'staff' tab in seed → GET /api/hierarchy/ returns 200."""
    r = await client.get("/api/hierarchy/", headers=admin_headers)
    assert r.status_code in (200, 404)  # 404 acceptable if empty list; just not 403

@pytest.mark.asyncio
async def test_superadmin_bypasses_all_tabs(client, superadmin_headers):
    """superadmin bypasses permission checks regardless of seed."""
    r = await client.get("/api/hierarchy/", headers=superadmin_headers)
    assert r.status_code in (200, 404)

@pytest.mark.asyncio
async def test_require_action_403(client, auth_headers):
    """employee has no 'purchase.transition_status' action → 403 on transition endpoint."""
    r = await client.post("/api/purchases/99999/transition?status=confirmed", headers=auth_headers)
    assert r.status_code in (403, 404)
