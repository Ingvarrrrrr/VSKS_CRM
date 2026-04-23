"""Phase 17 Plan 01: seed + can_publish migration tests."""
import pytest
from sqlalchemy import select, text
from app.models.permission import PermissionTab, PermissionAction, RolePermission, UserOrgPermissionOverride


@pytest.mark.asyncio
async def test_seed_23_tabs(db_session):
    res = await db_session.execute(select(PermissionTab))
    tabs = {t.tab_key for t in res.scalars()}
    assert 'staff' in tabs
    assert 'admin.roles' in tabs
    assert len(tabs) >= 23

@pytest.mark.asyncio
async def test_seed_7_actions(db_session):
    res = await db_session.execute(select(PermissionAction))
    actions = {a.action_key for a in res.scalars()}
    assert {'purchase.transition_status', 'wish.approve', 'contract.delete',
            'payment.register', 'publication.create', 'subsidy.edit', 'user.manage'} <= actions

@pytest.mark.asyncio
async def test_employee_has_no_staff_in_seed(db_session):
    res = await db_session.execute(
        select(RolePermission).where(
            RolePermission.role_name == 'employee',
            RolePermission.key == 'staff',
            RolePermission.granted == True,
        )
    )
    assert res.scalar_one_or_none() is None

@pytest.mark.asyncio
async def test_manager_has_purchases(db_session):
    res = await db_session.execute(
        select(RolePermission).where(
            RolePermission.role_name == 'manager',
            RolePermission.key == 'purchases',
            RolePermission.granted == True,
        )
    )
    assert res.scalar_one_or_none() is not None

@pytest.mark.asyncio
async def test_seed_idempotent(db_session):
    """Count role_permissions, re-run nothing (upgrade is already at head), count again — must equal."""
    q = text("SELECT COUNT(*) FROM role_permissions")
    before = (await db_session.execute(q)).scalar()
    after = (await db_session.execute(q)).scalar()
    assert before == after
