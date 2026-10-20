# -*- coding: utf-8 -*-
"""Аудит безопасности 2026-10-20 (поведенческий фаззинг, bt_b_owner): DELETE
/api/users/{свой_id} отдавал 204 для ЛЮБОЙ роли, а если удаляемый был хозяином
аккаунта (Organization.owner_user_id), организация оставалась БЕЗ хозяина.

Покрывает три дыры той же природы (Правило №6 — один хелпер
app.auth.permissions.assert_not_last_account_owner на все три):
  1) DELETE /api/users/{id} — самоудаление (любая роль) и удаление последнего
     хозяина аккаунта (кем бы его ни удаляли).
  2) PATCH /api/users/{id} — account_owner меняет СВОЮ роль с account_owner на
     другую, будучи хозяином хотя бы одной организации.
  3) DELETE /api/hierarchy/api/users/{uid}/organizations/{org_id} — выход из
     организации, хозяином которой числится сам пользователь.

Легитимные случаи не должны ломаться: удаление сотрудника БЕЗ owner_user_id
админом/account_owner по-прежнему работает (существующие тесты/поведенческий
чек-лист это покрывают отдельно).
"""
import uuid

import pytest
from sqlalchemy import select

from app.auth.permissions import assert_not_last_account_owner, get_owned_organization_ids
from app.models.organization import Organization
from app.models.contractor import Contractor
from fastapi import HTTPException


async def _make_org(db_session, owner_user_id=None):
    name = f"SelfDelOrg-{uuid.uuid4().hex[:8]}"
    contractor = Contractor(name=name)
    db_session.add(contractor)
    await db_session.flush()
    org = Organization(contractor_id=contractor.id, owner_user_id=owner_user_id)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


# ---------------------------------------------------------------------------
# Хелпер: get_owned_organization_ids / assert_not_last_account_owner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_helper_detects_owned_org(db_session, make_user):
    owner = await make_user(role="account_owner")
    org = await _make_org(db_session, owner_user_id=owner.id)

    owned = await get_owned_organization_ids(owner.id, db_session)
    assert org.id in owned

    with pytest.raises(HTTPException) as exc_info:
        await assert_not_last_account_owner(owner.id, db_session, action="удалить сотрудника")
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_helper_noop_for_non_owner(db_session, make_user):
    employee = await make_user(role="employee")
    owned = await get_owned_organization_ids(employee.id, db_session)
    assert owned == []
    # не должно бросать
    await assert_not_last_account_owner(employee.id, db_session, action="удалить сотрудника")


# ---------------------------------------------------------------------------
# 1) DELETE /api/users/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_self_forbidden_for_any_role(client, db_session, test_org, make_user):
    from app.auth.jwt import create_access_token

    actor = await make_user(role="admin", org_id=test_org.id)
    token = create_access_token({"sub": actor.username, "org_id": actor.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.delete(f"/api/users/{actor.id}", headers=headers)
    assert resp.status_code == 409, resp.text

    # Учётка жива
    from app.models.user import User
    still_there = (await db_session.execute(
        select(User).where(User.id == actor.id)
    )).scalar_one_or_none()
    assert still_there is not None


@pytest.mark.asyncio
async def test_delete_last_account_owner_forbidden(client, db_session, test_org, make_user):
    from app.auth.jwt import create_access_token

    owner = await make_user(role="account_owner", org_id=test_org.id)
    org = await _make_org(db_session, owner_user_id=owner.id)

    superadmin = await make_user(role="superadmin")
    token = create_access_token({"sub": superadmin.username, "org_id": superadmin.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.delete(f"/api/users/{owner.id}", headers=headers)
    assert resp.status_code == 409, resp.text
    # Глобальный обработчик HTTPException (app/errors.py) кладёт текст в
    # "message", не в "detail" — см. http_exception_handler.
    assert "хозяин" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_delete_regular_employee_still_works(client, db_session, test_org, make_user):
    """Контроль: удаление сотрудника без owner_user_id по-прежнему 200."""
    from app.auth.jwt import create_access_token

    actor = await make_user(role="admin", org_id=test_org.id)
    victim = await make_user(role="employee", org_id=test_org.id)
    token = create_access_token({"sub": actor.username, "org_id": actor.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.delete(f"/api/users/{victim.id}", headers=headers)
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 2) PATCH /api/users/{id} — смена своей роли с account_owner на ниже
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_cannot_demote_self_while_owning_org(client, db_session, test_org, make_user):
    from app.auth.jwt import create_access_token

    owner = await make_user(role="account_owner", org_id=test_org.id)
    await _make_org(db_session, owner_user_id=owner.id)

    token = create_access_token({"sub": owner.username, "org_id": owner.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.patch(
        f"/api/users/{owner.id}", json={"role": "employee"}, headers=headers
    )
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# 3) DELETE .../organizations/{org_id} — выход из своей организации
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_cannot_leave_own_organization(client, db_session, test_org, make_user):
    from app.auth.jwt import create_access_token

    owner = await make_user(role="account_owner", org_id=test_org.id)
    test_org.owner_user_id = owner.id
    await db_session.commit()

    token = create_access_token({"sub": owner.username, "org_id": owner.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.delete(
        f"/api/users/{owner.id}/organizations/{test_org.id}", headers=headers
    )
    assert resp.status_code == 409, resp.text
