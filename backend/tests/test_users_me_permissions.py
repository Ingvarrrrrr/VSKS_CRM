"""Phase 17 Plan 03: /users/me?org_id returns effective tabs+actions."""
import pytest


@pytest.mark.asyncio
async def test_me_returns_permissions_object(client, admin_headers, test_admin_user):
    r = await client.get(f"/api/users/me?org_id={test_admin_user.org_id}", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert 'permissions' in body
    assert 'tabs' in body['permissions']
    assert 'actions' in body['permissions']

@pytest.mark.asyncio
async def test_me_admin_sees_staff_tab(client, admin_headers, test_admin_user):
    r = await client.get(f"/api/users/me?org_id={test_admin_user.org_id}", headers=admin_headers)
    assert 'staff' in r.json()['permissions']['tabs']

@pytest.mark.asyncio
async def test_me_employee_no_staff_tab(client, auth_headers, test_user):
    r = await client.get(f"/api/users/me?org_id={test_user.org_id}", headers=auth_headers)
    assert 'staff' not in r.json()['permissions']['tabs']

@pytest.mark.asyncio
async def test_me_override_flips_bit(client, auth_headers, test_user, user_org_access, make_override):
    """Grant 'staff' to employee via override → /users/me reflects it."""
    await make_override(user_org_access.id, 'staff', True)
    r = await client.get(f"/api/users/me?org_id={test_user.org_id}", headers=auth_headers)
    assert 'staff' in r.json()['permissions']['tabs']
