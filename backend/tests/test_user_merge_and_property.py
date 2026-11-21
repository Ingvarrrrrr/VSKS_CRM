"""
Tests for user merge service (app.services.user_merge) and property asset categorization.
"""
import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.user import User
from app.models.organization import Organization
from app.models.contractor import Contractor
from app.models.task import Task
from app.models.vehicle import Vehicle
from app.services.user_merge import merge_users


async def _make_org(db_session, name_prefix="Org"):
    c = Contractor(name=f"{name_prefix}-{uuid.uuid4().hex[:8]}")
    db_session.add(c)
    await db_session.flush()
    org = Organization(name=c.name, contractor_id=c.id)
    db_session.add(org)
    await db_session.flush()
    org.root_org_id = org.id
    await db_session.commit()
    await db_session.refresh(org)
    return org


async def _make_user(db_session, org_id, role="employee", email_prefix="user"):
    u = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:6]}@example.com",
        username=f"{email_prefix}-{uuid.uuid4().hex[:6]}",
        password_hash="testpasshash",
        org_id=org_id,
        role=role,
        full_name="Иванов Иван",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.mark.asyncio
async def test_merge_users_self_merge_forbidden(db_session):
    """Слияние пользователя самого с собой запрещено (400)."""
    org = await _make_org(db_session, "MergeOrg1")
    admin = await _make_user(db_session, org.id, role="admin", email_prefix="admin1")
    u1 = await _make_user(db_session, org.id, email_prefix="u1")

    with pytest.raises(HTTPException) as exc:
        await merge_users(u1.id, [u1.id], admin, db_session)
    assert exc.value.status_code == 400
    assert "совпадает с основным" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_merge_users_foreign_org_forbidden(db_session):
    """Слияние пользователей из чужой организации / контура запрещено (404/403)."""
    org1 = await _make_org(db_session, "MergeOrgA")
    org2 = await _make_org(db_session, "MergeOrgB")

    admin1 = await _make_user(db_session, org1.id, role="admin", email_prefix="adminA")
    u1 = await _make_user(db_session, org1.id, email_prefix="uA")
    u_foreign = await _make_user(db_session, org2.id, email_prefix="uB")

    with pytest.raises(HTTPException) as exc:
        await merge_users(u1.id, [u_foreign.id], admin1, db_session)
    assert exc.value.status_code in (403, 404)


@pytest.mark.asyncio
async def test_merge_users_repoints_tasks(db_session):
    """При слиянии связанные сущности (например, Task) переносятся на целевого пользователя."""
    org = await _make_org(db_session, "MergeOrgTask")
    admin = await _make_user(db_session, org.id, role="admin", email_prefix="adminT")
    keep_user = await _make_user(db_session, org.id, email_prefix="keep")
    dup_user = await _make_user(db_session, org.id, email_prefix="dup")

    task = Task(
        title="Тестовая задача",
        org_id=org.id,
        created_by_id=dup_user.id,
        assigned_user_id=dup_user.id,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    result = await merge_users(keep_user.id, [dup_user.id], admin, db_session)
    assert result["ok"] is True
    assert result["merged_count"] == 1

    await db_session.refresh(task)
    assert task.assigned_user_id == keep_user.id
    assert task.created_by_id == keep_user.id


@pytest.mark.asyncio
async def test_property_category_isolation(db_session):
    """Имущество категорий 'equipment' и 'other' изолировано от ТС."""
    org = await _make_org(db_session, "PropOrg")

    v_car = Vehicle(
        owner_org_id=org.id,
        brand="Lada",
        model="Vesta",
        type="car_light",
        plate="A123BC77",
    )
    v_eq = Vehicle(
        owner_org_id=org.id,
        brand="Lenovo",
        model="ThinkPad",
        type="equipment",
        plate="ИНВ-001",
    )
    v_other = Vehicle(
        owner_org_id=org.id,
        brand="Шкаф металлический",
        type="other",
        plate="ИНВ-002",
    )
    db_session.add_all([v_car, v_eq, v_other])
    await db_session.commit()

    eq_rows = (await db_session.execute(
        select(Vehicle).where(Vehicle.owner_org_id == org.id, Vehicle.type == "equipment")
    )).scalars().all()
    assert len(eq_rows) == 1
    assert eq_rows[0].brand == "Lenovo"

    other_rows = (await db_session.execute(
        select(Vehicle).where(Vehicle.owner_org_id == org.id, Vehicle.type == "other")
    )).scalars().all()
    assert len(other_rows) == 1
    assert other_rows[0].brand == "Шкаф металлический"

    car_rows = (await db_session.execute(
        select(Vehicle).where(Vehicle.owner_org_id == org.id, Vehicle.type == "car_light")
    )).scalars().all()
    assert len(car_rows) == 1
    assert car_rows[0].brand == "Lada"
