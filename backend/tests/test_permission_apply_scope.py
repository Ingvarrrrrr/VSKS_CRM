"""Владелец 2026-09-02: «нужно чтобы при доступе ко всем организациям были
разные настройки именно для всех организаций».

До этой правки PUT /api/permissions/users/{user_id}/overrides у ЦЕЛЕВОГО
пользователя с включённым users.all_orgs_access ВСЕГДА веером применял
правку ко всем организациям его охвата (см. Владелец 2026-09-01, п.4) —
настроить организации по-разному было невозможно. Теперь веер — по явному
query-параметру apply_to_all (default False): без него правка задевает
только org_id из запроса, даже если у пользователя включён охват; с
apply_to_all=true — прежнее поведение (все org_id контура).

Эти тесты бьют по фактическому состоянию UserOrgPermissionOverride в БД
(не по коду ответа), чтобы отловить регресс, если веер снова станет
безусловным.
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.organization import Organization
from app.models.user_org_access import UserOrgAccess
from app.models.permission import UserOrgPermissionOverride


async def _make_org(db_session) -> Organization:
    org = Organization(name=f"TestOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


async def _ensure_uoa(db_session, user_id, org_id, role) -> UserOrgAccess:
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


async def _override_granted(db_session, uoa_id, key) -> bool | None:
    """Возвращает granted для (uoa_id, key), либо None если оверрайда нет."""
    res = await db_session.execute(
        select(UserOrgPermissionOverride.granted).where(
            UserOrgPermissionOverride.user_org_access_id == uoa_id,
            UserOrgPermissionOverride.key == key,
        )
    )
    row = res.scalar_one_or_none()
    return row


async def _setup_all_orgs_access_target(db_session, test_org, make_user):
    """Employee с включённым all_orgs_access и членством в двух независимых
    организациях (org1 = test_org, org2 — отдельный корень). anchor-орги для
    get_all_orgs_access_org_ids — primary org_id ∪ UOA-орги, оба независимые
    корни без parent/owner связи дают контур ровно {org1, org2}."""
    org2 = await _make_org(db_session)
    target = await make_user(role="employee", org_id=test_org.id, all_orgs_access=True)
    uoa1 = await _ensure_uoa(db_session, target.id, test_org.id, "employee")
    uoa2 = await _ensure_uoa(db_session, target.id, org2.id, "employee")
    return target, org2, uoa1, uoa2


@pytest.mark.asyncio
async def test_default_apply_to_all_false_touches_only_selected_org(
    client, superadmin_headers, test_org, make_user, db_session
):
    """Без apply_to_all правка задевает ТОЛЬКО org_id из query, даже если у
    целевого пользователя включён all_orgs_access и есть охват на org2."""
    target, org2, uoa1, uoa2 = await _setup_all_orgs_access_target(db_session, test_org, make_user)

    resp = await client.put(
        f"/api/permissions/users/{target.id}/overrides?org_id={test_org.id}",
        headers=superadmin_headers,
        json=[{"key": "purchases", "granted": True}],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied_org_ids"] == [test_org.id]

    # Фактическое состояние БД — источник правды, не код ответа.
    assert await _override_granted(db_session, uoa1.id, "purchases") is True
    assert await _override_granted(db_session, uoa2.id, "purchases") is None


@pytest.mark.asyncio
async def test_apply_to_all_true_fans_out_to_full_scope(
    client, superadmin_headers, test_org, make_user, db_session
):
    """С apply_to_all=true — прежнее поведение: веер по всем организациям
    охвата целевого пользователя (Владелец 2026-09-01, п.4)."""
    target, org2, uoa1, uoa2 = await _setup_all_orgs_access_target(db_session, test_org, make_user)

    resp = await client.put(
        f"/api/permissions/users/{target.id}/overrides?org_id={test_org.id}&apply_to_all=true",
        headers=superadmin_headers,
        json=[{"key": "purchases", "granted": True}],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["applied_org_ids"]) == {test_org.id, org2.id}

    assert await _override_granted(db_session, uoa1.id, "purchases") is True
    assert await _override_granted(db_session, uoa2.id, "purchases") is True
