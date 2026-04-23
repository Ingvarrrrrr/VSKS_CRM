"""Phase 17 Plan 05: D-09 superadmin invisible to non-superadmin."""
import pytest


@pytest.mark.asyncio
async def test_list_users_excludes_superadmin_for_non_superadmin(client, admin_headers, superadmin_user):
    r = await client.get("/api/users/", headers=admin_headers)
    assert r.status_code == 200
    ids = {u['id'] for u in r.json()}
    assert superadmin_user.id not in ids

@pytest.mark.asyncio
async def test_list_users_includes_superadmin_for_superadmin(client, superadmin_headers, superadmin_user):
    r = await client.get("/api/users/", headers=superadmin_headers)
    assert r.status_code == 200
    ids = {u['id'] for u in r.json()}
    assert superadmin_user.id in ids
