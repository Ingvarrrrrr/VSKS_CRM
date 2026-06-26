"""Phase 28: тесты для app.auth.visibility — get_visible_user_ids, get_view_all_org_ids, build_visibility_clause."""
import pytest
from app.auth.visibility import get_visible_user_ids, get_view_all_org_ids, build_visibility_clause


@pytest.mark.asyncio
async def test_superadmin_visible_is_none(db_session, superadmin_user):
    """SaaS-роль superadmin → None (без user-уровня фильтра)."""
    result = await get_visible_user_ids(superadmin_user, db_session)
    assert result is None


@pytest.mark.asyncio
async def test_employee_alone_sees_only_self(db_session, test_user):
    """Employee без иерархии видит только себя."""
    result = await get_visible_user_ids(test_user, db_session)
    assert result == {test_user.id}


@pytest.mark.asyncio
async def test_manager_sees_direct_subordinate(db_session, test_org, make_user):
    """Manager видит подчинённого через UserHierarchy.manager_id."""
    from app.models.user_hierarchy import UserHierarchy
    manager = await make_user(role="manager")
    subordinate = await make_user(role="employee")
    db_session.add(UserHierarchy(manager_id=manager.id, subordinate_id=subordinate.id))
    await db_session.commit()

    visible = await get_visible_user_ids(manager, db_session)
    assert manager.id in visible
    assert subordinate.id in visible


@pytest.mark.asyncio
async def test_transitive_hierarchy_3_levels(db_session, test_org, make_user):
    """A → B → C: A видит B и C (транзитивность через frontier-loop)."""
    from app.models.user_hierarchy import UserHierarchy
    a = await make_user(role="manager")
    b = await make_user(role="manager")
    c = await make_user(role="employee")
    db_session.add(UserHierarchy(manager_id=a.id, subordinate_id=b.id))
    db_session.add(UserHierarchy(manager_id=b.id, subordinate_id=c.id))
    await db_session.commit()

    visible = await get_visible_user_ids(a, db_session)
    assert {a.id, b.id, c.id} <= visible


@pytest.mark.asyncio
async def test_dept_head_sees_dept_members(db_session, test_org, make_user):
    """Department.head_user_id видит всех членов отдела."""
    from app.models.department import Department
    from app.models.user_organization import UserOrganization
    head = await make_user(role="manager")
    member1 = await make_user(role="employee")
    member2 = await make_user(role="employee")
    dept = Department(name="TestDept", org_id=test_org.id, head_user_id=head.id)
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    db_session.add(UserOrganization(user_id=member1.id, org_id=test_org.id, dept_id=dept.id))
    db_session.add(UserOrganization(user_id=member2.id, org_id=test_org.id, dept_id=dept.id))
    await db_session.commit()

    visible = await get_visible_user_ids(head, db_session)
    assert {head.id, member1.id, member2.id} <= visible


@pytest.mark.asyncio
async def test_dept_manager_sees_uo_only_members(db_session, test_org, make_user):
    """ManagerDepartment видит члена отдела, заведённого ТОЛЬКО через UserOrganization.dept_id."""
    from app.models.department import Department
    from app.models.user_organization import UserOrganization
    from app.models.manager_department import ManagerDepartment
    manager = await make_user(role="manager")
    member = await make_user(role="employee")
    dept = Department(name="ManagedDept", org_id=test_org.id)
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    db_session.add(ManagerDepartment(manager_user_id=manager.id, dept_id=dept.id))
    db_session.add(UserOrganization(user_id=member.id, org_id=test_org.id, dept_id=dept.id))
    await db_session.commit()

    visible = await get_visible_user_ids(manager, db_session)
    assert member.id in visible


@pytest.mark.asyncio
async def test_view_all_org_ids_empty_without_action(db_session, test_user, user_org_access):
    """Без action documents.view_all_in_org → пустой set."""
    result = await get_view_all_org_ids(test_user, db_session)
    assert result == set()


@pytest.mark.asyncio
async def test_view_all_org_ids_with_role_permission(db_session, test_user, user_org_access, make_role_permission):
    """С role_permission granted=true для 'documents.view_all_in_org' → org в set."""
    await make_role_permission(role=test_user.role, key="documents.view_all_in_org", granted=True)
    result = await get_view_all_org_ids(test_user, db_session)
    assert test_user.org_id in result


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_type", ["purchase", "task", "wish", "contract"])
async def test_build_clause_returns_or_for_non_saas(db_session, test_user, doc_type):
    """Для non-SaaS role build_visibility_clause возвращает не-None."""
    clause = await build_visibility_clause(test_user, db_session, doc_type)
    assert clause is not None


@pytest.mark.asyncio
async def test_build_clause_returns_none_for_superadmin(db_session, superadmin_user):
    """Для SaaS-роли (superadmin) — None (без фильтра)."""
    clause = await build_visibility_clause(superadmin_user, db_session, "purchase")
    assert clause is None


@pytest.mark.asyncio
async def test_build_clause_invalid_doc_type(db_session, test_user):
    """Невалидный doc_type → ValueError."""
    with pytest.raises(ValueError):
        await build_visibility_clause(test_user, db_session, "frobnicator")
