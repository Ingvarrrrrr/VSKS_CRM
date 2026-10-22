# -*- coding: utf-8 -*-
"""Правило владельца (22.10.2026): «На чьё имя заявка» (Wish.assigned_to)
может быть только сотрудник, устроенный в организации субсидии ЗАЯВКИ —
то же правило, что уже проверяет инициатора/адресата служебной записки
закупки (app/services/service_note_people.py, тест
test_service_note_people_staff.py). Общее ядро — assert_people_in_subsidy_staff
(ПРАВИЛО №6, формула штата не дублируется, читаем из
app.services.service_note_initiators.org_staff_user_ids).

Три места, где Wish.assigned_to реально меняется (проверено grep'ом):
  - app/routers/wishes.py::create_wish (создание заявки)
  - app/routers/wishes.py::update_wish (PUT, полная правка автором/участником)
  - app/routers/wish_transitions.py::patch_wish_execution (PATCH /execution,
    согласующий/менеджер+)

Приёмы — по образцу test_wish_org_from_subsidy.py: прямой вызов роутер-функций
с db_session, без HTTP-клиента (эти функции принимают db/current_user как
обычные Python-объекты, FastAPI Depends тут не участвует)."""
import uuid

import pytest
from fastapi import HTTPException

from app.models.subsidy import Subsidy
from app.models.wish import Wish
from app.routers.wishes import create_wish, update_wish
from app.routers.wish_transitions import patch_wish_execution
from app.schemas.wishes import WishCreate, WishUpdate, WishExecutionPatch


async def _make_subsidy(db_session, org_id, name="AssignedToStaff subsidy") -> Subsidy:
    s = Subsidy(name=f"{name}-{uuid.uuid4().hex[:8]}", year=2026, budget=0, org_id=org_id, status="approved")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


@pytest.mark.asyncio
async def test_create_wish_staff_assignee_passes(db_session, test_org, make_user):
    # account_owner — чтобы не упереться в видимость субсидии (employee без
    # грантов её по умолчанию не видит, см. test_wish_org_from_subsidy.py);
    # предмет этого теста — проверка штата исполнителя, не видимость.
    author = await make_user(role="account_owner", org_id=test_org.id)
    staffer = await make_user(role="employee", org_id=test_org.id)
    subsidy = await _make_subsidy(db_session, test_org.id)

    out = await create_wish(
        body=WishCreate(title="Заявка со штатным исполнителем", subsidy_id=subsidy.id, assigned_to=staffer.id),
        db=db_session, current_user=author,
    )
    assert out.assigned_to == staffer.id


@pytest.mark.asyncio
async def test_create_wish_org_access_only_assignee_rejected(db_session, test_org, make_user):
    """Персональный user_org_access без штата (primary org_id/membership) —
    не штат, 400 при создании заявки."""
    from app.models.organization import Organization
    from app.models.contractor import Contractor
    from app.models.user_org_access import UserOrgAccess

    other_contractor = Contractor(name=f"OtherOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(other_contractor)
    await db_session.flush()
    other_org = Organization(contractor_id=other_contractor.id)
    db_session.add(other_org)
    await db_session.commit()
    await db_session.refresh(other_org)

    author = await make_user(role="account_owner", org_id=test_org.id)
    outsider = await make_user(role="employee", org_id=other_org.id)
    db_session.add(UserOrgAccess(user_id=outsider.id, org_id=test_org.id, role="employee"))
    await db_session.commit()
    subsidy = await _make_subsidy(db_session, test_org.id)

    with pytest.raises(HTTPException) as exc:
        await create_wish(
            body=WishCreate(title="Заявка не-штатному", subsidy_id=subsidy.id, assigned_to=outsider.id),
            db=db_session, current_user=author,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "SERVICE_NOTE_PERSON_NOT_STAFF"


@pytest.mark.asyncio
async def test_create_wish_subsidy_access_only_assignee_rejected(db_session, test_org, make_user):
    """Персональный user_subsidy_access без штата — тоже не штат, 400."""
    from app.models.organization import Organization
    from app.models.contractor import Contractor
    from app.models.user_subsidy_access import UserSubsidyAccess

    other_contractor = Contractor(name=f"OtherOrg2-{uuid.uuid4().hex[:8]}")
    db_session.add(other_contractor)
    await db_session.flush()
    other_org = Organization(contractor_id=other_contractor.id)
    db_session.add(other_org)
    await db_session.commit()
    await db_session.refresh(other_org)

    author = await make_user(role="account_owner", org_id=test_org.id)
    outsider = await make_user(role="employee", org_id=other_org.id)
    subsidy = await _make_subsidy(db_session, test_org.id)
    db_session.add(UserSubsidyAccess(user_id=outsider.id, subsidy_id=subsidy.id, role="org_admin"))
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await create_wish(
            body=WishCreate(title="Заявка не-штатному 2", subsidy_id=subsidy.id, assigned_to=outsider.id),
            db=db_session, current_user=author,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_wish_unchanged_assignee_not_checked(db_session, test_org, make_user):
    """Старая заявка с уже сохранённым (возможно не-штатным) assigned_to —
    PUT без ИЗМЕНЕНИЯ этого поля не должен падать (фронт шлёт поле в каждом
    запросе) — та же гарантия, что у service_note_by в purchases.py."""
    from app.models.organization import Organization
    from app.models.contractor import Contractor

    other_contractor = Contractor(name=f"OtherOrg3-{uuid.uuid4().hex[:8]}")
    db_session.add(other_contractor)
    await db_session.flush()
    other_org = Organization(contractor_id=other_contractor.id)
    db_session.add(other_org)
    await db_session.commit()
    await db_session.refresh(other_org)

    author = await make_user(role="employee", org_id=test_org.id)
    outsider = await make_user(role="employee", org_id=other_org.id)
    subsidy = await _make_subsidy(db_session, test_org.id)

    wish = Wish(
        org_id=test_org.id, title="Старая заявка с чужим исполнителем",
        subsidy_id=subsidy.id, status="draft", created_by=author.id,
        assigned_to=outsider.id,
    )
    db_session.add(wish)
    await db_session.commit()
    await db_session.refresh(wish)

    out = await update_wish(
        wish_id=wish.id,
        body=WishUpdate(assigned_to=outsider.id, title="Пересохранение без смены исполнителя"),
        db=db_session, current_user=author,
    )
    assert out.title == "Пересохранение без смены исполнителя"
    assert out.assigned_to == outsider.id


@pytest.mark.asyncio
async def test_update_wish_changes_subsidy_and_assignee_checks_new_subsidy(db_session, make_user):
    """Смена субсидии и assigned_to ОДНОВРЕМЕННО — проверяем штат по НОВОЙ
    субсидии (владелец, 22.10.2026)."""
    from app.models.organization import Organization
    from app.models.contractor import Contractor

    org_old_c = Contractor(name=f"OldOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(org_old_c)
    await db_session.flush()
    org_old = Organization(contractor_id=org_old_c.id)
    db_session.add(org_old)
    await db_session.commit()
    await db_session.refresh(org_old)

    org_new_c = Contractor(name=f"NewOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(org_new_c)
    await db_session.flush()
    org_new = Organization(contractor_id=org_new_c.id, root_org_id=org_old.id)
    db_session.add(org_new)
    await db_session.commit()
    await db_session.refresh(org_new)

    owner = await make_user(role="account_owner", org_id=org_old.id)
    org_old.owner_user_id = owner.id
    db_session.add(org_old)
    await db_session.commit()

    staffer_new_org = await make_user(role="employee", org_id=org_new.id)

    subsidy_old = await _make_subsidy(db_session, org_old.id, name="Old")
    subsidy_new = await _make_subsidy(db_session, org_new.id, name="New")

    created = await create_wish(
        body=WishCreate(title="Заявка до смены субсидии и исполнителя", subsidy_id=subsidy_old.id),
        db=db_session, current_user=owner,
    )

    # staffer_new_org не штат старой субсидии (org_old) — если бы проверка
    # шла по СТАРОЙ субсидии, тут было бы 400. Проверяем по новой — штат
    # org_new, должно пройти.
    out = await update_wish(
        wish_id=created.id,
        body=WishUpdate(subsidy_id=subsidy_new.id, assigned_to=staffer_new_org.id),
        db=db_session, current_user=owner,
    )
    assert out.assigned_to == staffer_new_org.id
    wish = await db_session.get(Wish, created.id)
    assert wish.subsidy_id == subsidy_new.id
    assert wish.org_id == org_new.id


@pytest.mark.asyncio
async def test_patch_execution_rejects_outsider_assignee(db_session, test_org, make_user):
    from app.models.organization import Organization
    from app.models.contractor import Contractor

    other_contractor = Contractor(name=f"OtherOrg4-{uuid.uuid4().hex[:8]}")
    db_session.add(other_contractor)
    await db_session.flush()
    other_org = Organization(contractor_id=other_contractor.id)
    db_session.add(other_org)
    await db_session.commit()
    await db_session.refresh(other_org)

    owner = await make_user(role="account_owner", org_id=test_org.id)
    outsider = await make_user(role="employee", org_id=other_org.id)
    subsidy = await _make_subsidy(db_session, test_org.id)

    wish = Wish(
        org_id=test_org.id, title="Заявка на исполнении",
        subsidy_id=subsidy.id, status="submitted", created_by=owner.id,
    )
    db_session.add(wish)
    await db_session.commit()
    await db_session.refresh(wish)

    with pytest.raises(HTTPException) as exc:
        await patch_wish_execution(
            wish_id=wish.id,
            body=WishExecutionPatch(assigned_to=outsider.id),
            db=db_session, current_user=owner,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "SERVICE_NOTE_PERSON_NOT_STAFF"


@pytest.mark.asyncio
async def test_patch_execution_accepts_staff_assignee(db_session, test_org, make_user):
    owner = await make_user(role="account_owner", org_id=test_org.id)
    staffer = await make_user(role="employee", org_id=test_org.id)
    subsidy = await _make_subsidy(db_session, test_org.id)

    wish = Wish(
        org_id=test_org.id, title="Заявка на исполнении 2",
        subsidy_id=subsidy.id, status="submitted", created_by=owner.id,
    )
    db_session.add(wish)
    await db_session.commit()
    await db_session.refresh(wish)

    out = await patch_wish_execution(
        wish_id=wish.id,
        body=WishExecutionPatch(assigned_to=staffer.id),
        db=db_session, current_user=owner,
    )
    assert out.assigned_to == staffer.id
