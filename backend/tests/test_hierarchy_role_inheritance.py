"""Phase 28: тесты для has_role_via_hierarchy и наследования ролей через иерархию."""
import pytest
from app.auth.jwt import has_role_via_hierarchy


@pytest.mark.asyncio
async def test_user_with_role_in_set(db_session, test_admin_user):
    """user.role in roles → True (прямое совпадение без обращения к иерархии)."""
    assert await has_role_via_hierarchy(test_admin_user, db_session, "org_admin", "admin")


@pytest.mark.asyncio
async def test_user_without_role_no_hierarchy(db_session, test_user):
    """employee без подчинённых, не в whitelist → False."""
    result = await has_role_via_hierarchy(test_user, db_session, "admin", "superadmin")
    assert not result


@pytest.mark.asyncio
async def test_inherit_role_via_hierarchy(db_session, test_org, make_user):
    """Wave 3: superadmin НЕ наследуется через иерархию (невидим/недостижим),
    но обычные роли (admin) — наследуются."""
    from app.models.user_hierarchy import UserHierarchy
    manager = await make_user(role="manager")
    super_sub = await make_user(role="superadmin")
    admin_sub = await make_user(role="admin")
    db_session.add(UserHierarchy(manager_id=manager.id, subordinate_id=super_sub.id))
    db_session.add(UserHierarchy(manager_id=manager.id, subordinate_id=admin_sub.id))
    await db_session.commit()

    assert not await has_role_via_hierarchy(manager, db_session, "superadmin")
    assert await has_role_via_hierarchy(manager, db_session, "admin")


@pytest.mark.asyncio
async def test_no_inherit_after_link_removed(db_session, test_org, make_user):
    """Manager без подчинённых с ролью superadmin → не наследует."""
    manager = await make_user(role="manager")
    # Нет строк в user_hierarchy
    assert not await has_role_via_hierarchy(manager, db_session, "superadmin")


@pytest.mark.asyncio
async def test_superadmin_not_inherited_via_hierarchy(db_session, test_org, make_user):
    """Wave 3: require_superadmin-уровень НЕ достигается через подчинённого-суперадмина."""
    from app.models.user_hierarchy import UserHierarchy

    manager = await make_user(role="manager")
    super_sub = await make_user(role="superadmin")
    db_session.add(UserHierarchy(manager_id=manager.id, subordinate_id=super_sub.id))
    await db_session.commit()

    assert not await has_role_via_hierarchy(manager, db_session, "superadmin")


@pytest.mark.asyncio
async def test_employee_without_hierarchy_blocked(client, test_user, auth_headers):
    """Обычный employee → 403 на require_superadmin endpoint."""
    resp = await client.get("/api/organizations/", headers=auth_headers)
    assert resp.status_code == 403
