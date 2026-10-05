"""Владелец (2026-10-06): «Владелец аккаунта может всё. Он один в аккаунте,
может быть передан, но он один». На проде это было не так:
- role_permissions для account_owner стояли granted=False на admin.billing/
  admin.organizations/subsidy.correct (и один ключ не существовал совсем) —
  владелец не видел «Биллинг» в меню;
- в карточке сотрудника владелец, открыв СЕБЯ, видел всё заблокированным
  (isHierarchyBlocked перебивал исключение для self-edit).

Единое место фикса — app/auth/permissions.py::_get_effective_simple (bypass
account_owner ДО чтения role_permissions/overrides) и
::assert_can_manage_user_access (account_owner обходит ранговую проверку и
self-edit guard целиком, кроме цели-superadmin). Этот файл фиксирует
итоговое поведение через HTTP/функции, которые используют именно эти точки —
второй формулы "владелец = всё" эти тесты не создают."""
import pytest
from sqlalchemy import select

from app.auth.permissions import get_effective_actions
from app.models.permission import RolePermission
from app.models.user_org_access import UserOrgAccess


def _headers_for(user):
    from app.auth.jwt import create_access_token
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


async def _force_role_permission(db_session, role_name, key, granted):
    """Force a role_permissions row to a specific granted value, bypassing the
    seed — simulates the prod drift described in the docstring above."""
    res = await db_session.execute(
        select(RolePermission).where(
            RolePermission.role_name == role_name,
            RolePermission.key == key,
        )
    )
    row = res.scalar_one_or_none()
    if row is None:
        db_session.add(RolePermission(role_name=role_name, key=key, granted=granted))
    else:
        row.granted = granted
    await db_session.commit()


# ---------------------------------------------------------------------------
# 1) /users/me: account_owner получает admin.billing + subsidy.correct, даже
#    если role_permissions для них стоит granted=False (дрейф с прода).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_gets_billing_and_subsidy_correct_despite_false_in_matrix(
    db_session, test_org, make_user, client,
):
    await _force_role_permission(db_session, "account_owner", "admin.billing", False)
    await _force_role_permission(db_session, "account_owner", "subsidy.correct", False)

    owner = await make_user(role="account_owner", org_id=test_org.id)
    resp = await client.get("/api/users/me", headers=_headers_for(owner))
    assert resp.status_code == 200
    perms = resp.json()["permissions"]
    assert "admin.billing" in perms["actions"] or "admin.billing" in perms["tabs"]
    assert "subsidy.correct" in perms["actions"]


@pytest.mark.asyncio
async def test_owner_effective_actions_ignore_role_matrix_false(db_session, test_org, make_user):
    """Same guarantee at the function level (get_effective_actions), independent
    of the /users/me HTTP wrapper — the real source of truth is
    _get_effective_simple."""
    await _force_role_permission(db_session, "account_owner", "admin.billing", False)
    owner = await make_user(role="account_owner", org_id=test_org.id)
    actions = await get_effective_actions(owner, db_session, org_id=test_org.id)
    assert "admin.billing" in actions


# ---------------------------------------------------------------------------
# 2) Владелец меняет допуски сотрудника с ролью org_admin.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_can_manage_org_admin_overrides(db_session, test_org, make_user, client):
    owner = await make_user(role="account_owner", org_id=test_org.id)
    org_admin = await make_user(role="org_admin", org_id=test_org.id)
    db_session.add(UserOrgAccess(user_id=org_admin.id, org_id=test_org.id, role="org_admin"))
    await db_session.commit()

    resp = await client.put(
        f"/api/permissions/users/{org_admin.id}/overrides?org_id={test_org.id}",
        headers=_headers_for(owner),
        json=[{"key": "admin.roles", "granted": True}],
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3) Владелец меняет допуски самому себе — исключение из self-edit guard.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_can_edit_own_permissions(db_session, test_org, make_user, client):
    owner = await make_user(role="account_owner", org_id=test_org.id)
    db_session.add(UserOrgAccess(user_id=owner.id, org_id=test_org.id, role="account_owner"))
    await db_session.commit()

    resp = await client.put(
        f"/api/permissions/users/{owner.id}/overrides?org_id={test_org.id}",
        headers=_headers_for(owner),
        json=[{"key": "purchases", "granted": True}],
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 4) org_admin по-прежнему НЕ может менять org_admin и выше (регресс).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_admin_still_cannot_manage_org_admin_or_above(
    client, test_admin_user, admin_headers, test_org, make_user,
):
    other_admin = await make_user(role="org_admin", org_id=test_org.id)
    resp = await client.put(
        f"/api/permissions/users/{other_admin.id}/overrides?org_id={test_org.id}",
        headers=admin_headers,
        json=[{"key": "admin.roles", "granted": True}],
    )
    assert resp.status_code == 403

    owner = await make_user(role="account_owner", org_id=test_org.id)
    resp2 = await client.put(
        f"/api/permissions/users/{owner.id}/overrides?org_id={test_org.id}",
        headers=admin_headers,
        json=[{"key": "admin.roles", "granted": True}],
    )
    assert resp2.status_code == 403
