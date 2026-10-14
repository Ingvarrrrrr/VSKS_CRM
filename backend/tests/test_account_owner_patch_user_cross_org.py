"""Баг (владелец, 2026-10-14): PATCH /api/users/{id} для account_owner сравнивал
user.org_id != current_user.org_id напрямую — но account_owner может иметь
НЕСКОЛЬКО организаций в контуре аккаунта (Organization.root_org_id-дерево +
owner_user_id-связь, см. app/auth/visibility.py::compute_account_contour_org_ids),
а target-сотрудник мог относиться к ЛЮБОЙ из них (через user.org_id или через
доп. допуск UserOrgAccess), а не только к primary-орге владельца.

Исправлено app/auth/permissions.py::assert_target_in_owner_account — канонический
расчёт контура (get_account_contour_org_ids), без второго механизма (Правило №6).

Тесты бьют напрямую по HTTP PATCH /api/users/{id} (там была дыра), через общий
`client` fixture (см. conftest.py)."""
import uuid

import pytest
from sqlalchemy import select

from app.auth.jwt import create_access_token
from app.models.organization import Organization
from app.models.user import User


async def _make_org(db_session, *, root_org_id=None, owner_user_id=None):
    org = Organization(name=f"TestOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()
    org.root_org_id = org.id if root_org_id is None else root_org_id
    org.owner_user_id = owner_user_id
    await db_session.commit()
    await db_session.refresh(org)
    return org


def _headers_for(user):
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_account_owner_can_patch_employee_in_sibling_org_of_own_account(
    client, db_session, make_user,
):
    """owner правит сотрудника дочерней организации своего аккаунта
    (child_org.root_org_id указывает на орг владельца) — 200."""
    owner = await make_user(role="account_owner")
    root_org = await _make_org(db_session, owner_user_id=owner.id)
    owner.org_id = root_org.id
    await db_session.commit()
    await db_session.refresh(owner)

    child_org = await _make_org(db_session, root_org_id=root_org.id)
    employee = await make_user(role="employee", org_id=child_org.id)

    resp = await client.patch(
        f"/api/users/{employee.id}",
        headers=_headers_for(owner),
        json={"all_orgs_access": True},
    )

    assert resp.status_code == 200, resp.text
    res = await db_session.execute(select(User).where(User.id == employee.id))
    refreshed = res.scalar_one()
    assert refreshed.all_orgs_access is True


@pytest.mark.asyncio
async def test_account_owner_cannot_patch_employee_of_another_account(
    client, db_session, make_user,
):
    """Сотрудник из чужого дерева организаций (другой root_org_id, другой
    owner_user_id) — 403, аккаунты не пересекаются."""
    owner = await make_user(role="account_owner")
    root_org = await _make_org(db_session, owner_user_id=owner.id)
    owner.org_id = root_org.id
    await db_session.commit()
    await db_session.refresh(owner)

    other_owner = await make_user(role="account_owner")
    other_root_org = await _make_org(db_session, owner_user_id=other_owner.id)
    stranger = await make_user(role="employee", org_id=other_root_org.id)

    resp = await client.patch(
        f"/api/users/{stranger.id}",
        headers=_headers_for(owner),
        json={"all_orgs_access": True},
    )

    assert resp.status_code == 403
    message = resp.json().get("message", "")
    assert "не относится к организациям" in message.lower() or "нет доступа" in message.lower()
