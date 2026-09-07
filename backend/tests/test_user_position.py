"""Тесты единственного резолвера/писателя должности (app.services.user_position).

Волна D2, Правило №6: должность сотрудника хранилась дважды (users.position и
user_organizations.position) с двумя писателями и двумя читателями с разным
fallback. Здесь проверяем сам хелпер (без HTTP) и его поведение через
PUT/PATCH /api/users/{id} (единственное новое поведение — 422 при нескольких
членствах без явной организации).
"""
import pytest
from app.services.user_position import (
    resolve_user_position,
    set_user_position,
    UserPositionAmbiguousOrgError,
    UserPositionNoMembershipError,
    POSITION_UNSET,
)


class _FakeUser:
    def __init__(self, id=1, position=None):
        self.id = id
        self.position = position


class _FakeMembership:
    def __init__(self, id, org_id, position):
        self.id = id
        self.org_id = org_id
        self.position = position


# ---------------------------------------------------------------------------
# resolve_user_position — pure function, no DB
# ---------------------------------------------------------------------------

def test_resolve_no_memberships_falls_back_to_legacy():
    user = _FakeUser(position="Legacy Position")
    assert resolve_user_position(user, org_id=None, memberships=[]) == "Legacy Position"
    assert resolve_user_position(user, org_id=5, memberships=[]) == "Legacy Position"


def test_resolve_no_memberships_no_legacy_returns_none():
    user = _FakeUser(position=None)
    assert resolve_user_position(user, org_id=None, memberships=[]) is None


def test_resolve_org_id_matches_specific_membership():
    user = _FakeUser(position="Legacy Position")
    memberships = [
        _FakeMembership(1, org_id=10, position="Менеджер в орг 10"),
        _FakeMembership(2, org_id=20, position="Директор в орг 20"),
    ]
    assert resolve_user_position(user, org_id=10, memberships=memberships) == "Менеджер в орг 10"
    assert resolve_user_position(user, org_id=20, memberships=memberships) == "Директор в орг 20"


def test_resolve_org_id_no_matching_membership_does_not_leak_other_org():
    """Rule #6: должность из ЧУЖОЙ организации не подставляется — членство
    есть, но не для запрошенной org_id, легаси тоже не подмешиваем (членства
    у пользователя есть, просто не в этой org)."""
    user = _FakeUser(position="Legacy Position")
    memberships = [_FakeMembership(1, org_id=10, position="Менеджер в орг 10")]
    assert resolve_user_position(user, org_id=99, memberships=memberships) is None


def test_resolve_single_membership_no_org_id():
    user = _FakeUser(position="Legacy Position")
    memberships = [_FakeMembership(1, org_id=10, position="Единственная должность")]
    assert resolve_user_position(user, org_id=None, memberships=memberships) == "Единственная должность"


def test_resolve_multiple_memberships_no_org_id_picks_first_by_id():
    """Правило, ранее жившее только в routers/hierarchy.py — сохранено."""
    user = _FakeUser(position="Legacy Position")
    memberships = [
        _FakeMembership(5, org_id=20, position="Вторая по id"),
        _FakeMembership(2, org_id=10, position="Первая по id"),
    ]
    assert resolve_user_position(user, org_id=None, memberships=memberships) == "Первая по id"


def test_resolve_multiple_memberships_skips_empty_positions():
    user = _FakeUser(position="Legacy Position")
    memberships = [
        _FakeMembership(1, org_id=10, position=None),
        _FakeMembership(2, org_id=20, position="Есть значение"),
    ]
    assert resolve_user_position(user, org_id=None, memberships=memberships) == "Есть значение"


# ---------------------------------------------------------------------------
# set_user_position — DB-backed (пишет в реальные UserOrganization строки)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_user_position_with_membership_arg_writes_directly(db_session, test_user, test_org):
    from app.models.user_organization import UserOrganization
    uo = UserOrganization(user_id=test_user.id, org_id=test_org.id, position="Старая")
    db_session.add(uo)
    await db_session.commit()
    await db_session.refresh(uo)

    result = await set_user_position(db_session, "Новая должность", membership=uo)
    assert result is uo
    assert uo.position == "Новая должность"


@pytest.mark.asyncio
async def test_set_user_position_org_id_single_membership(db_session, test_user, test_org):
    from app.models.user_organization import UserOrganization
    uo = UserOrganization(user_id=test_user.id, org_id=test_org.id, position=None)
    db_session.add(uo)
    await db_session.commit()

    await set_user_position(db_session, "Инженер", user=test_user, org_id=test_org.id)
    await db_session.commit()
    await db_session.refresh(uo)
    assert uo.position == "Инженер"


@pytest.mark.asyncio
async def test_set_user_position_org_id_no_membership_raises(db_session, test_user, test_org):
    with pytest.raises(UserPositionNoMembershipError):
        await set_user_position(db_session, "Инженер", user=test_user, org_id=999999)


@pytest.mark.asyncio
async def test_set_user_position_no_org_zero_memberships_writes_legacy(db_session, test_user):
    await set_user_position(db_session, "Только легаси", user=test_user, org_id=None)
    await db_session.commit()
    await db_session.refresh(test_user)
    assert test_user.position == "Только легаси"


@pytest.mark.asyncio
async def test_set_user_position_no_org_single_membership_writes_it(db_session, test_user, test_org):
    from app.models.user_organization import UserOrganization
    uo = UserOrganization(user_id=test_user.id, org_id=test_org.id, position=None)
    db_session.add(uo)
    await db_session.commit()

    await set_user_position(db_session, "Единственная", user=test_user, org_id=None)
    await db_session.commit()
    await db_session.refresh(uo)
    assert uo.position == "Единственная"


@pytest.mark.asyncio
async def test_set_user_position_no_org_multiple_memberships_raises_ambiguous(db_session, test_user, test_org):
    import uuid
    from app.models.organization import Organization
    from app.models.user_organization import UserOrganization
    org2 = Organization(name=f"TestOrg2-{uuid.uuid4().hex[:8]}")
    db_session.add(org2)
    await db_session.commit()
    await db_session.refresh(org2)

    db_session.add(UserOrganization(user_id=test_user.id, org_id=test_org.id, position="A"))
    db_session.add(UserOrganization(user_id=test_user.id, org_id=org2.id, position="B"))
    await db_session.commit()

    with pytest.raises(UserPositionAmbiguousOrgError):
        await set_user_position(db_session, "Новая", user=test_user, org_id=None)


# ---------------------------------------------------------------------------
# HTTP-level: PATCH /api/users/{id} — единственное новое поведение (422)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_user_position_multi_org_without_org_id_returns_422(
    client, db_session, test_admin_user, admin_headers,
):
    """Пользователь без legacy department/org_id, но с двумя членствами —
    PATCH .../position без указания организации обязан вернуть 422 с понятной
    причиной, а не молча выбрать одну из организаций или упасть 500."""
    import uuid
    from app.models.user import User
    from app.models.organization import Organization
    from app.models.user_organization import UserOrganization
    from app.auth.jwt import hash_password

    org_a = Organization(name=f"OrgA-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"OrgB-{uuid.uuid4().hex[:8]}")
    db_session.add_all([org_a, org_b])
    await db_session.commit()
    await db_session.refresh(org_a)
    await db_session.refresh(org_b)

    multi_org_user = User(
        username=f"multi_org_{uuid.uuid4().hex[:8]}",
        password_hash=hash_password("testpass123"),
        role="employee",
        org_id=None,       # нет legacy primary org
        department=None,   # нет legacy department
        full_name="Мульти Орг Тестов",
    )
    db_session.add(multi_org_user)
    await db_session.commit()
    await db_session.refresh(multi_org_user)

    db_session.add(UserOrganization(user_id=multi_org_user.id, org_id=org_a.id, position="Менеджер"))
    db_session.add(UserOrganization(user_id=multi_org_user.id, org_id=org_b.id, position="Директор"))
    await db_session.commit()

    resp = await client.patch(
        f"/api/users/{multi_org_user.id}",
        json={"position": "Новая должность"},
        headers=admin_headers,
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert "организац" in str(body).lower()
