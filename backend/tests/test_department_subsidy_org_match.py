"""Правило владельца (28.10.2026): форма отдела показывает только субсидии
ВЫБРАННОЙ организации — бэкенд (app/routers/departments.py::
_assert_subsidy_org_matches) перепроверяет то же самое при сохранении, не
доверяя фронту. Субсидия другой организации — 422, не тихое сохранение.
"""
import uuid

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def test_org_b(db_session):
    from app.models.contractor import Contractor
    from app.models.organization import Organization
    name = f"TestOrgB-{uuid.uuid4().hex[:8]}"
    contractor = Contractor(name=name)
    db_session.add(contractor)
    await db_session.flush()
    org = Organization(contractor_id=contractor.id)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def subsidy_org_b(db_session, test_org_b):
    from app.models.subsidy import Subsidy
    sub = Subsidy(name=f"Subsidy B {uuid.uuid4().hex[:8]}", year=2026, org_id=test_org_b.id, status="approved")
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


@pytest_asyncio.fixture
async def subsidy_org_a(db_session, test_org):
    from app.models.subsidy import Subsidy
    sub = Subsidy(name=f"Subsidy A {uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id, status="approved")
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


@pytest.mark.asyncio
async def test_create_department_rejects_subsidy_from_other_org(
    client, test_org, subsidy_org_b, superadmin_headers,
):
    resp = await client.post(
        "/api/departments/",
        json={"name": f"Отдел {uuid.uuid4().hex[:6]}", "org_id": test_org.id, "subsidy_id": subsidy_org_b.id},
        headers=superadmin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "другой организации" in resp.text


@pytest.mark.asyncio
async def test_create_department_accepts_subsidy_from_same_org(
    client, test_org, subsidy_org_a, superadmin_headers,
):
    resp = await client.post(
        "/api/departments/",
        json={"name": f"Отдел {uuid.uuid4().hex[:6]}", "org_id": test_org.id, "subsidy_id": subsidy_org_a.id},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["subsidy_id"] == subsidy_org_a.id


@pytest.mark.asyncio
async def test_update_department_rejects_subsidy_from_other_org(
    client, test_org, subsidy_org_b, superadmin_headers,
):
    create_resp = await client.post(
        "/api/departments/",
        json={"name": f"Отдел {uuid.uuid4().hex[:6]}", "org_id": test_org.id},
        headers=superadmin_headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    dept_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/departments/{dept_id}",
        json={"subsidy_id": subsidy_org_b.id},
        headers=superadmin_headers,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_admin_cannot_create_department_in_unrelated_org(
    client, test_org_b, admin_headers,
):
    """admin_headers — org_admin test_org'a (не test_org_b). Чужой org_id
    из тела запроса не должен молча применяться (ИСПРАВЛЕНИЕ 28.10.2026)."""
    resp = await client.post(
        "/api/departments/",
        json={"name": f"Отдел {uuid.uuid4().hex[:6]}", "org_id": test_org_b.id},
        headers=admin_headers,
    )
    assert resp.status_code == 403, resp.text
