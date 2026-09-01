"""2026-09-01: организация не может остаться «ничейной» вне контура ни одного
аккаунта. Регрессия: суперадмин создавал org standalone-веткой без
root_org_id вовсе (organizations.py) — так региональные отделения ВСКС стали
организациями-сиротами. Единая точка правды теперь —
app.services.org_account_resolution.resolve_new_org_root_id, используется и в
POST /api/organizations/ (organizations.py), и в
_materialize_org_from_contractor (subsidies.py). Единственное легитимное
исключение — POST /api/register (создание НОВОГО аккаунта): проверяется
отдельным тестом ниже.
"""
import pytest
from sqlalchemy import select

from app.models.organization import Organization


@pytest.mark.asyncio
async def test_superadmin_create_org_without_root_defaults_to_own_account(
    client, superadmin_headers, superadmin_user,
):
    """Superadmin не указал root_org_id явно → org уходит под аккаунт самого
    superadmin (истинный корень его org_id), а не остаётся ничейной."""
    r = await client.post(
        "/api/organizations/",
        json={"name": "Filial_no_explicit_root"},
        headers=superadmin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["root_org_id"] is not None
    assert body["root_org_id"] == superadmin_user.org_id


@pytest.mark.asyncio
async def test_superadmin_create_org_with_explicit_root_org_id(
    client, db_session, superadmin_headers, test_org,
):
    """Superadmin явно выбрал ДРУГОЙ аккаунт (root_org_id в теле запроса) →
    новая org привязывается именно к нему."""
    other_root = Organization(name="Other_Account_Root")
    db_session.add(other_root)
    await db_session.commit()
    await db_session.refresh(other_root)

    r = await client.post(
        "/api/organizations/",
        json={"name": "Filial_of_other_account", "root_org_id": other_root.id},
        headers=superadmin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["root_org_id"] == other_root.id


@pytest.mark.asyncio
async def test_account_owner_create_org_binds_to_own_account(
    client, db_session, make_user, test_org,
):
    """account_owner создаёт org → она уходит под его собственный аккаунт,
    как и раньше (behaviour unchanged)."""
    from app.auth.jwt import create_access_token

    owner = await make_user(role="account_owner", org_id=test_org.id)
    token = create_access_token({"sub": owner.username})
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/organizations/",
        json={"name": "Filial_of_own_account"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["root_org_id"] == test_org.id
    assert body["owner_user_id"] == owner.id


@pytest.mark.asyncio
async def test_account_owner_cannot_forge_root_org_id_to_other_account(
    client, db_session, make_user, test_org,
):
    """Security: account_owner не может привязать новую org к ЧУЖОМУ
    аккаунту, даже если подсунет root_org_id другого аккаунта в теле запроса —
    только superadmin вправе выбирать аккаунт явно."""
    from app.auth.jwt import create_access_token

    other_root = Organization(name="Other_Account_Root_2")
    db_session.add(other_root)
    await db_session.commit()
    await db_session.refresh(other_root)

    owner = await make_user(role="account_owner", org_id=test_org.id)
    token = create_access_token({"sub": owner.username})
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/organizations/",
        json={"name": "Filial_forged_root", "root_org_id": other_root.id},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["root_org_id"] == test_org.id
    assert body["root_org_id"] != other_root.id


@pytest.mark.asyncio
async def test_register_new_account_keeps_root_org_id_none(client, db_session):
    """Единственное легитимное исключение: POST /api/register создаёт корень
    НОВОГО аккаунта — его root_org_id должен остаться NULL (это и есть корень),
    а не проваливаться в resolve_new_org_root_id."""
    r = await client.post(
        "/api/register",
        json={
            "org_name": "Brand_New_Account_Root",
            "email": "brand_new_account_root_090126@example.com",
            "password": "throwaway-pass-090126",
            "full_name": "New Owner",
        },
    )
    assert r.status_code == 201, r.text

    org = (await db_session.execute(
        select(Organization).where(Organization.name == "Brand_New_Account_Root")
    )).scalars().first()
    assert org is not None
    assert org.root_org_id is None


@pytest.mark.asyncio
async def test_materialize_org_from_contractor_sets_root_org_id(db_session, test_org):
    """subsidies.py::_materialize_org_from_contractor (grantee-org auto-create
    for a subsidy's contractor) — тот же баг-класс, тот же фикс: новая org не
    должна остаться без root_org_id."""
    from app.models.contractor import Contractor
    from app.routers.subsidies import _materialize_org_from_contractor

    contractor = Contractor(name="Grantee_Contractor_090126", inn="7700000001")
    db_session.add(contractor)
    await db_session.commit()
    await db_session.refresh(contractor)

    org = await _materialize_org_from_contractor(db_session, contractor, test_org.id)
    assert org is not None
    assert org.root_org_id == test_org.id


@pytest.mark.asyncio
async def test_materialize_org_from_contractor_without_account_context_raises(db_session):
    """Без аккаунта-контекста (fallback_org_id=None) и без явного выбора —
    честная ошибка, а не молчаливый NULL root_org_id."""
    from fastapi import HTTPException
    from app.models.contractor import Contractor
    from app.routers.subsidies import _materialize_org_from_contractor

    contractor = Contractor(name="Grantee_Contractor_Orphan_090126", inn="7700000002")
    db_session.add(contractor)
    await db_session.commit()
    await db_session.refresh(contractor)

    with pytest.raises(HTTPException) as exc_info:
        await _materialize_org_from_contractor(db_session, contractor, None)
    assert exc_info.value.status_code == 400
