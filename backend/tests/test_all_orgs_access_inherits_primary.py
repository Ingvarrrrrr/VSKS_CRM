"""Решение владельца продукта (2026-10-14): «Доступ ко всем организациям
аккаунта» (users.all_orgs_access) — в организациях аккаунта, где у сотрудника
НЕТ СВОИХ настроек вкладок/действий, действуют настройки его ОСНОВНОЙ
организации (users.org_id). Где свои настройки заданы — остаются свои.

Источник решения — app/auth/all_orgs_inheritance.py (единственная реализация,
Правило №6). Проверяется через видимость субсидий (get_visible_subsidy_ids —
прод-сценарий Филиппова: employee, override subsidies=true только в основной
орге, 14 субсидий соседней орги были скрыты) и через HTTP PUT overrides
(копирование унаследованных ключей ПЕРЕД применением точечной правки)."""
import uuid

import pytest
from sqlalchemy import select

from app.auth.jwt import create_access_token
from app.auth.visibility import get_visible_subsidy_ids
from app.models.organization import Organization
from app.models.subsidy import Subsidy
from app.models.user_org_access import UserOrgAccess
from app.models.permission import UserOrgPermissionOverride


async def _make_org(db_session, *, root_org_id=None):
    org = Organization(name=f"TestOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()
    org.root_org_id = org.id if root_org_id is None else root_org_id
    await db_session.commit()
    await db_session.refresh(org)
    return org


def _headers_for(user):
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


async def _ensure_uoa(db_session, user_id, org_id, role=None):
    uoa = (await db_session.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == user_id, UserOrgAccess.org_id == org_id
        )
    )).scalar_one_or_none()
    if uoa is None:
        uoa = UserOrgAccess(user_id=user_id, org_id=org_id, role=role)
        db_session.add(uoa)
        await db_session.commit()
        await db_session.refresh(uoa)
    return uoa


async def _set_override(db_session, user_id, org_id, key, granted):
    uoa = await _ensure_uoa(db_session, user_id, org_id)
    db_session.add(UserOrgPermissionOverride(
        user_org_access_id=uoa.id, key=key, granted=granted,
    ))
    await db_session.commit()
    return uoa


async def _make_subsidy(db_session, org_id, name):
    subsidy = Subsidy(name=name, year=2026, org_id=org_id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)
    return subsidy


@pytest.mark.asyncio
async def test_all_orgs_access_inherits_subsidies_from_primary_org(db_session, make_user):
    """(a) employee c all_orgs_access, override subsidies=true ТОЛЬКО в
    основной орге → get_visible_subsidy_ids включает субсидии соседней орги
    того же аккаунта (прод-сценарий Филиппова)."""
    root = await _make_org(db_session)
    primary_org = await _make_org(db_session, root_org_id=root.id)
    neighbor_org = await _make_org(db_session, root_org_id=root.id)

    employee = await make_user(role="employee", org_id=primary_org.id, all_orgs_access=True)
    await _set_override(db_session, employee.id, primary_org.id, "subsidies", True)

    subsidy = await _make_subsidy(db_session, neighbor_org.id, "Sub-A")

    visible = await get_visible_subsidy_ids(employee, db_session)
    assert visible is not None
    assert subsidy.id in visible


@pytest.mark.asyncio
async def test_without_all_orgs_access_no_inheritance(db_session, make_user):
    """(b) та же настройка, но all_orgs_access ВЫКЛЮЧЕН → соседняя субсидия
    не видна."""
    root = await _make_org(db_session)
    primary_org = await _make_org(db_session, root_org_id=root.id)
    neighbor_org = await _make_org(db_session, root_org_id=root.id)

    employee = await make_user(role="employee", org_id=primary_org.id, all_orgs_access=False)
    await _set_override(db_session, employee.id, primary_org.id, "subsidies", True)

    subsidy = await _make_subsidy(db_session, neighbor_org.id, "Sub-B")

    visible = await get_visible_subsidy_ids(employee, db_session)
    assert visible is not None
    assert subsidy.id not in visible


@pytest.mark.asyncio
async def test_neighbor_own_overrides_block_inheritance(db_session, make_user):
    """(c) у соседней орги СВОИ overrides (subsidies=false) → наследование не
    применяется, своя настройка остаётся в силе."""
    root = await _make_org(db_session)
    primary_org = await _make_org(db_session, root_org_id=root.id)
    neighbor_org = await _make_org(db_session, root_org_id=root.id)

    employee = await make_user(role="employee", org_id=primary_org.id, all_orgs_access=True)
    await _set_override(db_session, employee.id, primary_org.id, "subsidies", True)
    await _set_override(db_session, employee.id, neighbor_org.id, "subsidies", False)

    subsidy = await _make_subsidy(db_session, neighbor_org.id, "Sub-C")

    visible = await get_visible_subsidy_ids(employee, db_session)
    assert visible is not None
    assert subsidy.id not in visible


@pytest.mark.asyncio
async def test_put_overrides_different_key_copies_inherited_first(client, db_session, make_user):
    """(d) PUT overrides в соседней орге по ДРУГОМУ ключу (purchases=false) —
    subsidies, унаследованное из основной орги, должно быть СКОПИРОВАНО в
    соседнюю орг ДО применения правки и остаться granted=True там же."""
    root = await _make_org(db_session)
    primary_org = await _make_org(db_session, root_org_id=root.id)
    neighbor_org = await _make_org(db_session, root_org_id=root.id)

    owner = await make_user(role="account_owner", org_id=root.id)
    employee = await make_user(role="employee", org_id=primary_org.id, all_orgs_access=True)
    await _set_override(db_session, employee.id, primary_org.id, "subsidies", True)
    # UOA в соседней орге существует, но БЕЗ overrides — тоже "своих настроек нет".
    await _ensure_uoa(db_session, employee.id, neighbor_org.id)

    resp = await client.put(
        f"/api/permissions/users/{employee.id}/overrides?org_id={neighbor_org.id}",
        headers=_headers_for(owner),
        json=[{"key": "purchases", "granted": False}],
    )
    assert resp.status_code == 200, resp.text

    from app.auth.all_orgs_inheritance import org_overrides_map
    neighbor_overrides = await org_overrides_map(employee.id, neighbor_org.id, db_session)
    assert neighbor_overrides.get("subsidies") is True
    assert neighbor_overrides.get("purchases") is False
