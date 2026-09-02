"""Phase (владелец, 2026-09-02): privilege-escalation guard tests.

Цыганов (org_admin) мог сам себе выдавать/запрещать допуски и даже назначить
себе роль account_owner через backend/app/routers/permissions.py — все
write-эндпоинты были защищены только require_tab("staff"), без иерархии
«кто кого настраивает».

Новое правило (см. app/auth/permissions.py::assert_can_manage_user_access):
- никто не правит свои собственные допуски/роль (кроме superadmin);
- настраивать чужие допуски можно только если ты СТРОГО выше по лестнице
  employee < manager < org_admin < admin < account_owner < superadmin;
- роль account_owner может назначить только superadmin или действующий
  account_owner.

Эти тесты бьют напрямую по HTTP-эндпоинтам permissions.py (не по внутренним
функциям), так как именно там была дыра.
"""
import pytest
from sqlalchemy import select
from app.models.user_org_access import UserOrgAccess


async def _ensure_uoa(db_session, user_id, org_id, role):
    """Directly create/update a UserOrgAccess row so overrides-endpoints see
    the target as a member (mirrors conftest's user_org_access fixture but
    parameterized for arbitrary users/roles)."""
    res = await db_session.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == user_id,
            UserOrgAccess.org_id == org_id,
        )
    )
    uoa = res.scalar_one_or_none()
    if uoa is None:
        uoa = UserOrgAccess(user_id=user_id, org_id=org_id, role=role)
        db_session.add(uoa)
        await db_session.commit()
        await db_session.refresh(uoa)
    return uoa


# ---------------------------------------------------------------------------
# (a) org_admin cannot grant a permission to himself
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_admin_cannot_grant_self_override(client, test_admin_user, admin_headers, test_org):
    resp = await client.put(
        f"/api/permissions/users/{test_admin_user.id}/overrides?org_id={test_org.id}",
        headers=admin_headers,
        json=[{"key": "admin.roles", "granted": True}],
    )
    assert resp.status_code == 403
    # Custom exception envelope: {"code","message","details","correlation_id"}
    # (see app-wide HTTPException handler) — NOT the plain FastAPI {"detail"}.
    message = resp.json().get("message", "")
    assert "хозяин аккаунта" in message.lower() or "суперадмин" in message.lower()


@pytest.mark.asyncio
async def test_org_admin_cannot_revoke_self_override_either(client, test_admin_user, admin_headers, test_org):
    """Rule 1 is bidirectional — self-lockout used to only block revoking
    admin.roles/staff; now ANY self-edit (grant or revoke, any key) is blocked."""
    resp = await client.put(
        f"/api/permissions/users/{test_admin_user.id}/overrides?org_id={test_org.id}",
        headers=admin_headers,
        json=[{"key": "purchases", "granted": False}],
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# (b) org_admin cannot assign himself the account_owner role
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_admin_cannot_self_promote_to_account_owner(client, test_admin_user, admin_headers, test_org):
    resp = await client.patch(
        f"/api/permissions/users/{test_admin_user.id}/role?org_id={test_org.id}",
        headers=admin_headers,
        json={"role": "account_owner"},
    )
    assert resp.status_code == 403
    message = resp.json().get("message", "")
    assert "хозяин аккаунта" in message.lower()


@pytest.mark.asyncio
async def test_org_admin_cannot_promote_someone_else_to_account_owner(
    client, test_admin_user, admin_headers, test_org, make_user
):
    """The account_owner-only-by-owner rule applies to ANY target, not just self."""
    employee = await make_user(role="employee", org_id=test_org.id)
    resp = await client.patch(
        f"/api/permissions/users/{employee.id}/role?org_id={test_org.id}",
        headers=admin_headers,
        json={"role": "account_owner"},
    )
    assert resp.status_code == 403
    message = resp.json().get("message", "")
    assert "хозяин аккаунта" in message.lower()


@pytest.mark.asyncio
async def test_org_admin_cannot_manage_another_org_admin(
    client, test_admin_user, admin_headers, test_org, make_user
):
    """Equal rank is not enough — must be STRICTLY higher."""
    other_admin = await make_user(role="org_admin", org_id=test_org.id)
    resp = await client.patch(
        f"/api/permissions/users/{other_admin.id}/role?org_id={test_org.id}",
        headers=admin_headers,
        json={"role": "manager"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# (c) org_admin CAN configure an employee (strictly below)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_admin_can_change_employee_role(
    client, test_admin_user, admin_headers, test_org, make_user, db_session
):
    employee = await make_user(role="employee", org_id=test_org.id)
    resp = await client.patch(
        f"/api/permissions/users/{employee.id}/role?org_id={test_org.id}",
        headers=admin_headers,
        json={"role": "manager"},
    )
    assert resp.status_code == 200
    res = await db_session.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == employee.id,
            UserOrgAccess.org_id == test_org.id,
        )
    )
    uoa = res.scalar_one()
    assert uoa.role == "manager"


@pytest.mark.asyncio
async def test_org_admin_can_grant_override_to_employee(
    client, test_admin_user, admin_headers, test_org, make_user, db_session
):
    employee = await make_user(role="employee", org_id=test_org.id)
    await _ensure_uoa(db_session, employee.id, test_org.id, "employee")
    resp = await client.put(
        f"/api/permissions/users/{employee.id}/overrides?org_id={test_org.id}",
        headers=admin_headers,
        json=[{"key": "purchases", "granted": True}],
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# (d) superadmin can do everything
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_superadmin_can_promote_to_account_owner(
    client, superadmin_headers, test_admin_user, test_org, db_session
):
    resp = await client.patch(
        f"/api/permissions/users/{test_admin_user.id}/role?org_id={test_org.id}",
        headers=superadmin_headers,
        json={"role": "account_owner"},
    )
    assert resp.status_code == 200
    res = await db_session.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == test_admin_user.id,
            UserOrgAccess.org_id == test_org.id,
        )
    )
    uoa = res.scalar_one()
    assert uoa.role == "account_owner"


@pytest.mark.asyncio
async def test_superadmin_can_grant_override_to_org_admin(
    client, superadmin_headers, test_admin_user, test_org, db_session
):
    await _ensure_uoa(db_session, test_admin_user.id, test_org.id, "org_admin")
    resp = await client.put(
        f"/api/permissions/users/{test_admin_user.id}/overrides?org_id={test_org.id}",
        headers=superadmin_headers,
        json=[{"key": "admin.roles", "granted": True}],
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_superadmin_can_edit_own_situation_freely(client, superadmin_headers, superadmin_user, test_org):
    """superadmin is the technical SaaS role — self-edit bypass still applies to it."""
    resp = await client.patch(
        f"/api/permissions/users/{superadmin_user.id}/role?org_id={test_org.id}",
        headers=superadmin_headers,
        json={"role": "admin"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Role-matrix (PUT /roles/{role_name}) hierarchy guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_admin_cannot_edit_own_role_matrix(client, admin_headers):
    resp = await client.put(
        "/api/permissions/roles/org_admin",
        headers=admin_headers,
        json=[{"key": "admin.roles", "granted": True}],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_org_admin_cannot_edit_higher_role_matrix(client, admin_headers):
    resp = await client.put(
        "/api/permissions/roles/account_owner",
        headers=admin_headers,
        json=[{"key": "admin.roles", "granted": True}],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_org_admin_can_edit_lower_role_matrix(client, admin_headers, db_session):
    resp = await client.put(
        "/api/permissions/roles/employee",
        headers=admin_headers,
        json=[{"key": "purchases", "granted": True}],
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_superadmin_can_edit_any_role_matrix(client, superadmin_headers):
    resp = await client.put(
        "/api/permissions/roles/account_owner",
        headers=superadmin_headers,
        json=[{"key": "staff", "granted": True}],
    )
    assert resp.status_code == 200
