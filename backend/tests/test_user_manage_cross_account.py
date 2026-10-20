# -*- coding: utf-8 -*-
"""Аудит безопасности 2026-10-20 (координатор подтвердил по коду): `delete_user`
(routers/users.py) проверял только `require_action('user.manage')` (есть ли
право ВООБЩЕ, в любой орге) + узкую org_admin-ветку — admin/account_owner
ЛЮБОГО аккаунта мог читать/менять/удалять пользователя ЧУЖОГО аккаунта по
известному id. Тот же класс дыры найден и закрыт в ~20 ручках с `{user_id}`/
`{uid}` одним хелпером `app.auth.permissions.assert_target_user_visible`
(контур — тот же канонический `get_account_contour_org_ids`, Правило №6):

  - users.py: GET/PATCH/DELETE /api/users/{id}
  - users_docs.py: photo/license-scan GET/PUT/DELETE, sync-contractor
  - users_platform_credentials.py: _assert_platform_access
  - hierarchy.py: .../organizations[/{org_id}], .../salary,
    .../org-memberships/{row_id}, .../task-authority
  - user_hierarchy.py: .../subordinates[/{sid}]
  - permissions.py: GET .../overrides, .../org-roles, .../subsidy-access(+overrides)
    (PUT/PATCH/DELETE там уже шли через assert_can_manage_user_access —
    усилен контуром там же, одним изменением на все 6 ручек)

Этот файл проверяет представительную выборку: users.py (GET/PATCH/DELETE) +
одну ручку из hierarchy.py (organizations) + одну из permissions.py
(overrides). Контроль: тот же actor внутри СВОЕГО аккаунта по-прежнему может
управлять своим сотрудником."""
import uuid

import pytest

from app.auth.jwt import create_access_token
from app.models.organization import Organization
from app.models.contractor import Contractor


async def _make_root_org(db_session):
    """Отдельное дерево организаций = отдельный аккаунт (свой root_org_id)."""
    name = f"XAcctOrg-{uuid.uuid4().hex[:8]}"
    contractor = Contractor(name=name)
    db_session.add(contractor)
    await db_session.flush()
    org = Organization(contractor_id=contractor.id)
    db_session.add(org)
    await db_session.flush()
    org.root_org_id = org.id
    await db_session.commit()
    await db_session.refresh(org)
    return org


def _headers_for(user):
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def two_accounts(db_session, make_user):
    """Два полностью разных аккаунта (разные root_org_id), в каждом свой
    admin и свой employee."""
    org_a = await _make_root_org(db_session)
    org_b = await _make_root_org(db_session)
    admin_a = await make_user(role="admin", org_id=org_a.id)
    employee_a = await make_user(role="employee", org_id=org_a.id)
    employee_b = await make_user(role="employee", org_id=org_b.id)
    return {
        "org_a": org_a, "org_b": org_b,
        "admin_a": admin_a, "employee_a": employee_a, "employee_b": employee_b,
    }


# ---------------------------------------------------------------------------
# users.py: GET / PATCH / DELETE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_cannot_get_foreign_account_user(client, two_accounts):
    resp = await client.get(
        f"/api/users/{two_accounts['employee_b'].id}",
        headers=_headers_for(two_accounts["admin_a"]),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_admin_cannot_patch_foreign_account_user(client, two_accounts):
    resp = await client.patch(
        f"/api/users/{two_accounts['employee_b'].id}",
        json={"department": "Чужой отдел"},
        headers=_headers_for(two_accounts["admin_a"]),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_admin_cannot_delete_foreign_account_user(client, db_session, two_accounts):
    from sqlalchemy import select
    from app.models.user import User

    resp = await client.delete(
        f"/api/users/{two_accounts['employee_b'].id}",
        headers=_headers_for(two_accounts["admin_a"]),
    )
    assert resp.status_code == 404, resp.text
    still_there = (await db_session.execute(
        select(User).where(User.id == two_accounts["employee_b"].id)
    )).scalar_one_or_none()
    assert still_there is not None


@pytest.mark.asyncio
async def test_admin_can_manage_own_account_user(client, two_accounts):
    """Контроль: тот же admin над сотрудником СВОЕГО аккаунта — работает."""
    resp = await client.get(
        f"/api/users/{two_accounts['employee_a'].id}",
        headers=_headers_for(two_accounts["admin_a"]),
    )
    assert resp.status_code == 200, resp.text

    resp = await client.patch(
        f"/api/users/{two_accounts['employee_a'].id}",
        json={"department": "Свой отдел"},
        headers=_headers_for(two_accounts["admin_a"]),
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# hierarchy.py: GET .../organizations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_cannot_read_foreign_account_user_organizations(client, two_accounts):
    resp = await client.get(
        f"/api/users/{two_accounts['employee_b'].id}/organizations",
        headers=_headers_for(two_accounts["admin_a"]),
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# permissions.py: GET .../overrides
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_cannot_read_foreign_account_user_overrides(client, two_accounts):
    resp = await client.get(
        f"/api/permissions/users/{two_accounts['employee_b'].id}/overrides",
        params={"org_id": two_accounts["org_b"].id},
        headers=_headers_for(two_accounts["admin_a"]),
    )
    assert resp.status_code == 404, resp.text
