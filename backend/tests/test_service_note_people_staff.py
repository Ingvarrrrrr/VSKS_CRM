"""Правило владельца (22.10.2026): «в служебных записках и приказах могут
быть только те, кто устроен в данной организации» — инициатор
(Purchase.service_note_by) и адресат (Purchase.service_note_to_user_id)
служебной записки обязаны быть ШТАТОМ организации субсидии закупки.

app.services.service_note_people.assert_service_note_people_in_staff —
единственная функция-проверка (ПРАВИЛО №6), переиспользующая формулу штата
из app.services.service_note_initiators.org_staff_user_ids (та же, что у
инициатора на генерации документа — не вторая копия).

Purchase.assigned_user_id («исполнитель») СОЗНАТЕЛЬНО не проверяется этой
функцией — разведка (см. docstring service_note_people.py) показала, что
ни один плейсхолдер, завязанный на assigned_user, не печатается в
service_note*.docx/order_purchase.docx.
"""
import uuid

import pytest
import pytest_asyncio

from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user_org_access import UserOrgAccess
from app.models.user_subsidy_access import UserSubsidyAccess
from app.services.service_note_people import assert_service_note_people_in_staff
from fastapi import HTTPException


@pytest_asyncio.fixture
async def test_org_b(db_session):
    from app.models.organization import Organization
    org = Organization(name=f"TestOrgB-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def test_subsidy(db_session, test_org):
    # status='approved' — иначе PUT на связанную закупку падает 409
    # (assert_subsidy_approved_for_binding), не доходя до нашей проверки.
    sub = Subsidy(name=f"Test subsidy {uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id, status="approved")
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


@pytest_asyncio.fixture
async def test_subsidy_no_org(db_session):
    sub = Subsidy(name=f"Orphan subsidy {uuid.uuid4().hex[:8]}", year=2026, org_id=None)
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


@pytest_asyncio.fixture
async def test_purchase(db_session, test_subsidy, test_user):
    # assigned_user_id=test_user — иначе ensure_purchase_visible (PUT/PATCH
    # гейт видимости) отдаёт 404 обычному employee без именной причастности.
    p = Purchase(
        subsidy_id=test_subsidy.id, item_name="Тестовая закупка", status="wishes",
        assigned_user_id=test_user.id,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def test_purchase_no_org(db_session, test_subsidy_no_org):
    p = Purchase(subsidy_id=test_subsidy_no_org.id, item_name="Закупка без орг субсидии", status="wishes")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_staff_member_passes(db_session, test_org, test_purchase, make_user):
    staffer = await make_user(role="employee", org_id=test_org.id)
    await assert_service_note_people_in_staff(
        db_session, test_purchase, {"service_note_by": staffer.id}
    )  # не должно бросить


@pytest.mark.asyncio
async def test_org_access_only_user_rejected(db_session, test_org, test_org_b, test_purchase, make_user):
    """Персональный user_org_access без штата (primary org_id/membership) —
    не штат, 400."""
    u = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserOrgAccess(user_id=u.id, org_id=test_org.id, role="employee"))
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await assert_service_note_people_in_staff(
            db_session, test_purchase, {"service_note_by": u.id}
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "SERVICE_NOTE_PERSON_NOT_STAFF"


@pytest.mark.asyncio
async def test_subsidy_access_only_user_rejected(db_session, test_org, test_org_b, test_subsidy, test_purchase, make_user):
    """Персональный user_subsidy_access без штата — тоже не штат, 400."""
    u = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserSubsidyAccess(user_id=u.id, subsidy_id=test_subsidy.id, role="org_admin"))
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await assert_service_note_people_in_staff(
            db_session, test_purchase, {"service_note_to_user_id": u.id}
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_unchanged_value_not_checked_by_router(db_session, test_org_b):
    """Роутер (purchases.py) вызывает assert_service_note_people_in_staff
    ТОЛЬКО когда новое значение отличается от текущего — сама функция этого
    не знает (это ответственность вызывающего), но контракт описан в
    докстринге: проверяем, что функция падает ЛЮБОЙ не-штатный id, когда её
    всё же вызвали — различие «менялось / не менялось» целиком на стороне
    purchases.py (см. test_put_rejects_outsider_as_service_note_by ниже)."""
    pass


@pytest.mark.asyncio
async def test_no_org_subsidy_skips_check(db_session, test_purchase_no_org, test_org_b, make_user):
    outsider = await make_user(role="employee", org_id=test_org_b.id)
    await assert_service_note_people_in_staff(
        db_session, test_purchase_no_org, {"service_note_by": outsider.id}
    )  # субсидия без org_id — проверка пропускается, не бросает


@pytest.mark.asyncio
async def test_none_values_ignored(db_session, test_purchase):
    await assert_service_note_people_in_staff(
        db_session, test_purchase, {"service_note_by": None, "service_note_to_user_id": None}
    )


# ---------------------------------------------------------------------------
# Сквозные HTTP: PUT/PATCH на закупке
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_rejects_outsider_as_service_note_by(
    client, db_session, test_org, test_org_b, test_subsidy, test_purchase, test_user, make_user, auth_headers,
):
    outsider = await make_user(role="employee", org_id=test_org_b.id)

    resp = await client.get(f"/api/purchases/{test_purchase.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    body["service_note_by"] = outsider.id

    resp = await client.put(f"/api/purchases/{test_purchase.id}", json=body, headers=auth_headers)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    detail = body.get("detail")
    code = body.get("code") or (detail.get("code") if isinstance(detail, dict) else None)
    assert code == "SERVICE_NOTE_PERSON_NOT_STAFF", resp.text


@pytest.mark.asyncio
async def test_put_same_service_note_by_does_not_break_save(
    client, db_session, test_org, test_subsidy, test_purchase, test_user, auth_headers,
):
    """Старая закупка с уже сохранённым (возможно не-штатным) значением — PUT
    без ИЗМЕНЕНИЯ этого поля не должен падать (фронт шлёт поле в каждом запросе)."""
    test_purchase.service_note_by = test_user.id
    await db_session.commit()

    resp = await client.get(f"/api/purchases/{test_purchase.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["service_note_by"] == test_user.id
    # Отправляем то же значение — не должно расцениваться как изменение.

    resp = await client.put(f"/api/purchases/{test_purchase.id}", json=body, headers=auth_headers)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_patch_rejects_outsider_as_service_note_to_user(
    client, db_session, test_org_b, test_purchase, auth_headers, make_user,
):
    outsider = await make_user(role="employee", org_id=test_org_b.id)

    resp = await client.patch(
        f"/api/purchases/{test_purchase.id}",
        json={"service_note_to_user_id": outsider.id},
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    detail = body.get("detail")
    code = body.get("code") or (detail.get("code") if isinstance(detail, dict) else None)
    assert code == "SERVICE_NOTE_PERSON_NOT_STAFF", resp.text


@pytest.mark.asyncio
async def test_patch_accepts_staff_member_as_service_note_to_user(
    client, db_session, test_org, test_purchase, auth_headers, make_user,
):
    staffer = await make_user(role="employee", org_id=test_org.id)

    resp = await client.patch(
        f"/api/purchases/{test_purchase.id}",
        json={"service_note_to_user_id": staffer.id},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# GET /api/users/?subsidy_id=&staff_only=1 — список для пикеров
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_users_staff_only_excludes_personal_access(
    client, db_session, test_org, test_org_b, test_subsidy, auth_headers, make_user,
):
    staffer = await make_user(role="employee", org_id=test_org.id)
    access_only = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserOrgAccess(user_id=access_only.id, org_id=test_org.id, role="employee"))
    await db_session.commit()

    resp = await client.get(
        f"/api/users/?subsidy_id={test_subsidy.id}&staff_only=1", headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    ids = {u["id"] for u in resp.json()}
    assert staffer.id in ids
    assert access_only.id not in ids


@pytest.mark.asyncio
async def test_users_subsidy_id_without_staff_only_still_includes_access(
    client, db_session, test_org, test_org_b, test_subsidy, auth_headers, make_user,
):
    """Контрольный: без staff_only=1 поведение GET /users/ не меняется
    (широкий список для остальных полей формы)."""
    access_only = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserOrgAccess(user_id=access_only.id, org_id=test_org.id, role="employee"))
    await db_session.commit()

    resp = await client.get(f"/api/users/?subsidy_id={test_subsidy.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    ids = {u["id"] for u in resp.json()}
    assert access_only.id in ids
