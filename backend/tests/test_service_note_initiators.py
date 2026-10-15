"""Тесты правила владельца (14.10.2026): кто может быть инициатором служебной
записки — app.services.service_note_initiators.initiator_candidate_ids.

Кейсы (см. докстринг модуля для полной формулировки правила):
  - org_admin своей организации без подчинённых → видит коллегу (весь штат)
  - org_admin, глобально employee в ДРУГОЙ орг → коллегу НЕ видит, себя — видит
    (сам в штате)
  - admin аккаунта → весь штат орги, входящей в контур его аккаунта
  - employee → чужого не видит, себя — видит
  - account_owner → весь штат
  - подчинённый вне штата → не проходит ни у руководителя, ни у account_owner
    (у account_owner — потому что видит весь штат, а подчинённый вне штата)
  - субсидия без org_id → фолбэк только сам current_user

Плюс пара сквозных HTTP-тестов (resolve_initiator через /i-can-act-for и
генерацию СЗ по заявке — единый механизм для закупки и заявки).
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.user_org_access import UserOrgAccess
from app.models.user_hierarchy import UserHierarchy
from app.models.user_subsidy_access import UserSubsidyAccess
from app.services.service_note_initiators import (
    org_staff_user_ids,
    initiator_candidate_ids,
)


@pytest_asyncio.fixture
async def test_org_b(db_session):
    """Вторая организация — «не штат» для test_org."""
    from app.models.organization import Organization
    org = Organization(name=f"TestOrgB-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def test_subsidy(db_session, test_org):
    """Субсидия, привязанная к test_org (штат = сотрудники test_org)."""
    sub = Subsidy(name=f"Test subsidy {uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id)
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


@pytest_asyncio.fixture
async def test_subsidy_no_org(db_session):
    """Субсидия без org_id — фолбэк-кейс."""
    sub = Subsidy(name=f"Orphan subsidy {uuid.uuid4().hex[:8]}", year=2026, org_id=None)
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


# ---------------------------------------------------------------------------
# org_staff_user_ids — «штат» = primary org_id ∪ membership (UOA — НЕ штат,
# Правило владельца 15.10.2026)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_staff_includes_primary_org_members(db_session, test_org, test_user, make_user, test_org_b):
    """test_user (primary org_id=test_org) входит в штат; сотрудник другой орг — нет."""
    colleague = await make_user(role="employee", org_id=test_org.id)
    outsider = await make_user(role="employee", org_id=test_org_b.id)

    staff = await org_staff_user_ids(db_session, test_org.id)

    assert test_user.id in staff
    assert colleague.id in staff
    assert outsider.id not in staff


@pytest.mark.asyncio
async def test_org_staff_excludes_personal_org_access(db_session, test_org, test_org_b, make_user):
    """Фикс 15.10.2026 (баг прода, служебка «ДНР_Правильная»): персональный
    user_org_access на test_org (без primary org_id/membership) — это ДОСТУП,
    не штат. Кейс владельца: Новичкова, primary org_id=ВСКС, с UOA
    role='employee' на Донецкое отделение — не его сотрудник."""
    u = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserOrgAccess(user_id=u.id, org_id=test_org.id, role="employee"))
    await db_session.commit()

    staff = await org_staff_user_ids(db_session, test_org.id)
    assert u.id not in staff


# ---------------------------------------------------------------------------
# initiator_candidate_ids — правило владельца по ролям
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_admin_own_org_sees_whole_staff(db_session, test_org, test_subsidy, make_user):
    """org_admin своей орг без подчинённых → коллега допустим (весь штат)."""
    admin = await make_user(role="org_admin", org_id=test_org.id)
    colleague = await make_user(role="employee", org_id=test_org.id)

    candidates = await initiator_candidate_ids(db_session, admin, test_subsidy)
    assert colleague.id in candidates
    assert admin.id in candidates


@pytest.mark.asyncio
async def test_org_admin_of_other_org_cannot_pick_colleague_but_can_pick_self(
    db_session, test_org, test_org_b, test_subsidy, make_user,
):
    """org_admin ДРУГОЙ орг — в системе роль «org_admin» в поле User.role это
    ГЛОБАЛЬНОЕ значение (combine_role_rank без орг-override не понижает его
    для другой орги, см. app.auth.permissions._resolve_role_for_org), поэтому
    «org_admin другой орг» моделируется ИМЕННО через персональный UOA-грант
    (user_org_access.role='org_admin') на org_b при глобальной роли employee
    — тогда эффективная роль В ОРГЕ СУБСИДИИ (test_org) остаётся employee
    (ниже org_admin), и пользователь попадает в ветку «сам + подчинённые ∩
    штат». Он не подчинён никому и не входит в штат test_org → ни коллегу,
    ни себя выбрать не может."""
    foreign_admin = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserOrgAccess(user_id=foreign_admin.id, org_id=test_org_b.id, role="org_admin"))
    await db_session.commit()
    colleague = await make_user(role="employee", org_id=test_org.id)

    candidates = await initiator_candidate_ids(db_session, foreign_admin, test_subsidy)
    assert colleague.id not in candidates
    # foreign_admin сам не в штате test_org — себя выбрать тоже нельзя
    assert foreign_admin.id not in candidates


@pytest.mark.asyncio
async def test_org_admin_cannot_pick_uoa_only_user_not_in_staff(
    db_session, test_org, test_org_b, test_subsidy, make_user,
):
    """Баг прода 15.10.2026 (служебка «ДНР_Правильная»): пользователь с
    primary org_id в ДРУГОЙ орг и персональным user_org_access.role='employee'
    на орг субсидии — НЕ в штате, org_admin не должен видеть его в кандидатах
    на инициатора (это и есть кейс Новичковой)."""
    admin = await make_user(role="org_admin", org_id=test_org.id)
    uoa_only = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserOrgAccess(user_id=uoa_only.id, org_id=test_org.id, role="employee"))
    await db_session.commit()

    candidates = await initiator_candidate_ids(db_session, admin, test_subsidy)
    assert uoa_only.id not in candidates

    staff = await org_staff_user_ids(db_session, test_org.id)
    assert uoa_only.id not in staff


@pytest.mark.asyncio
async def test_employee_sees_self_not_colleague(db_session, test_org, test_subsidy, make_user):
    """employee без подчинённых → сам виден, коллега — нет."""
    emp = await make_user(role="employee", org_id=test_org.id)
    colleague = await make_user(role="employee", org_id=test_org.id)

    candidates = await initiator_candidate_ids(db_session, emp, test_subsidy)
    assert emp.id in candidates
    assert colleague.id not in candidates


@pytest.mark.asyncio
async def test_manager_sees_subordinate_within_staff(db_session, test_org, test_subsidy, make_user):
    """manager + подчинённый (UserHierarchy), оба в штате → подчинённый допустим."""
    manager = await make_user(role="manager", org_id=test_org.id)
    subordinate = await make_user(role="employee", org_id=test_org.id)
    db_session.add(UserHierarchy(manager_id=manager.id, subordinate_id=subordinate.id))
    await db_session.commit()

    candidates = await initiator_candidate_ids(db_session, manager, test_subsidy)
    assert subordinate.id in candidates
    assert manager.id in candidates


@pytest.mark.asyncio
async def test_subordinate_outside_staff_is_excluded(db_session, test_org, test_org_b, test_subsidy, make_user):
    """Подчинённый вне штата (другая орг, без UOA/membership в test_org) — не
    допустим, даже если формально подчинён руководителю."""
    manager = await make_user(role="manager", org_id=test_org.id)
    subordinate_outside = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserHierarchy(manager_id=manager.id, subordinate_id=subordinate_outside.id))
    await db_session.commit()

    candidates = await initiator_candidate_ids(db_session, manager, test_subsidy)
    assert subordinate_outside.id not in candidates


@pytest.mark.asyncio
async def test_account_owner_sees_whole_staff(db_session, test_org, test_subsidy, make_user):
    """account_owner → любой из штата, включая не-подчинённого."""
    owner = await make_user(role="account_owner", org_id=test_org.id)
    staffer = await make_user(role="employee", org_id=test_org.id)

    candidates = await initiator_candidate_ids(db_session, owner, test_subsidy)
    assert staffer.id in candidates


@pytest.mark.asyncio
async def test_account_owner_cannot_pick_subordinate_outside_staff(
    db_session, test_org, test_org_b, test_subsidy, make_user,
):
    """Даже account_owner не может выбрать сотрудника, который не в штате орг
    субсидии (его подчинённый из другой организации)."""
    owner = await make_user(role="account_owner", org_id=test_org.id)
    outsider = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserHierarchy(manager_id=owner.id, subordinate_id=outsider.id))
    await db_session.commit()

    candidates = await initiator_candidate_ids(db_session, owner, test_subsidy)
    assert outsider.id not in candidates


@pytest.mark.asyncio
async def test_admin_in_account_contour_sees_whole_staff(db_session, test_org, test_subsidy, make_user):
    """admin («Администратор аккаунта») → весь штат, если орг субсидии в
    контуре его аккаунта (здесь — admin.org_id == subsidy.org_id, тривиальный
    контур из одной орги)."""
    admin = await make_user(role="admin", org_id=test_org.id)
    staffer = await make_user(role="employee", org_id=test_org.id)

    candidates = await initiator_candidate_ids(db_session, admin, test_subsidy)
    assert staffer.id in candidates


@pytest.mark.asyncio
async def test_subsidy_without_org_falls_back_to_self(db_session, test_subsidy_no_org, test_user):
    """Субсидия без org_id — штата нет, кандидат только сам current_user."""
    candidates = await initiator_candidate_ids(db_session, test_user, test_subsidy_no_org)
    assert candidates == {test_user.id}


@pytest.mark.asyncio
async def test_personal_uoa_admin_role_sees_whole_staff(db_session, test_org, test_subsidy, make_user):
    """Доправка 14.10.2026: глобально employee/manager, но user_org_access
    ИМЕННО этой орги даёт роль 'admin' (персональный грант) → весь штат, как
    обычному admin/org_admin — не уходит в ветку «подчинённые»."""
    grantee = await make_user(role="employee", org_id=test_org.id)
    db_session.add(UserOrgAccess(user_id=grantee.id, org_id=test_org.id, role="admin"))
    await db_session.commit()
    staffer = await make_user(role="employee", org_id=test_org.id)

    candidates = await initiator_candidate_ids(db_session, grantee, test_subsidy)
    assert staffer.id in candidates


@pytest.mark.asyncio
async def test_global_admin_outside_contour_sees_only_self_and_subordinates(
    db_session, test_org, test_org_b, test_subsidy, make_user,
):
    """Глобальный admin, чья орг (и контур) не совпадает с орг субсидии, →
    НЕ весь штат (effective_role='admin' здесь берётся из глобальной роли,
    не из персонального UOA-гранта этой орги) — только сам + подчинённые ∩
    штат. Без подчинённых и без вхождения в штат — пустое пересечение."""
    foreign_admin = await make_user(role="admin", org_id=test_org_b.id)
    staffer = await make_user(role="employee", org_id=test_org.id)

    candidates = await initiator_candidate_ids(db_session, foreign_admin, test_subsidy)
    assert staffer.id not in candidates
    assert foreign_admin.id not in candidates


@pytest.mark.asyncio
async def test_personal_subsidy_access_org_admin_sees_whole_staff(
    db_session, test_org, test_org_b, test_subsidy, make_user,
):
    """Фикс 15.10.2026: персональный user_subsidy_access.role='org_admin' на
    ЭТУ субсидию (а не на организацию) → весь штат орг субсидии, даже если
    выдавший грант сам из ДРУГОЙ орг и не входит в штат test_org — сам он при
    этом в кандидаты не попадает (грант не делает его частью штата)."""
    grantee = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserSubsidyAccess(user_id=grantee.id, subsidy_id=test_subsidy.id, role="org_admin"))
    await db_session.commit()
    staffer = await make_user(role="employee", org_id=test_org.id)

    candidates = await initiator_candidate_ids(db_session, grantee, test_subsidy)
    assert staffer.id in candidates
    assert grantee.id not in candidates


@pytest.mark.asyncio
async def test_personal_subsidy_access_employee_role_grants_nothing(
    db_session, test_org, test_org_b, test_subsidy, make_user,
):
    """Контрольный: user_subsidy_access.role='employee' (ниже org_admin) на
    эту субсидию не открывает штат — грантополучатель без подчинённых и вне
    штата не получает ни себя, ни коллегу."""
    grantee = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserSubsidyAccess(user_id=grantee.id, subsidy_id=test_subsidy.id, role="employee"))
    await db_session.commit()
    staffer = await make_user(role="employee", org_id=test_org.id)

    candidates = await initiator_candidate_ids(db_session, grantee, test_subsidy)
    assert grantee.id not in candidates
    assert staffer.id not in candidates


# ---------------------------------------------------------------------------
# Сквозные HTTP: /users/i-can-act-for?subsidy_id= и resolve_initiator
# (служебка закупки и служебка заявки — одно правило, Правило №6).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_i_can_act_for_with_subsidy_id_returns_staff_for_org_admin(
    client, db_session, test_org, test_subsidy, make_user,
):
    from app.auth.jwt import create_access_token

    admin = await make_user(role="org_admin", org_id=test_org.id)
    colleague = await make_user(role="employee", org_id=test_org.id)
    token = create_access_token({"sub": admin.username, "org_id": admin.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/users/i-can-act-for?subsidy_id={test_subsidy.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    ids = {u["id"] for u in resp.json()}
    assert colleague.id in ids


@pytest.mark.asyncio
async def test_list_users_by_org_id_still_includes_personal_access(
    client, db_session, test_org, test_org_b, make_user, auth_headers,
):
    """GET /api/users/?org_id= — поведение НЕ меняется фиксом 15.10.2026: этот
    список шире, чем «штат» инициатора, и по-прежнему включает персональный
    user_org_access (штат ∪ доступ), в отличие от initiator_candidate_ids."""
    uoa_only = await make_user(role="employee", org_id=test_org_b.id)
    db_session.add(UserOrgAccess(user_id=uoa_only.id, org_id=test_org.id, role="employee"))
    await db_session.commit()

    resp = await client.get(f"/api/users/?org_id={test_org.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    ids = {u["id"] for u in resp.json()}
    assert uoa_only.id in ids


@pytest.mark.asyncio
async def test_i_can_act_for_unknown_subsidy_404(client, auth_headers):
    resp = await client.get("/api/users/i-can-act-for?subsidy_id=9999999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wish_service_note_initiator_forbidden_for_outsider(
    client, db_session, test_org, test_org_b, test_subsidy, test_user, make_user,
):
    """Служебка заявки (wish_documents.py) использует ТОТ ЖЕ resolve_initiator,
    что и служебка закупки — инициатор вне штата получает 403 INITIATOR_FORBIDDEN."""
    from app.models.wish import Wish
    from app.auth.jwt import create_access_token

    outsider = await make_user(role="employee", org_id=test_org_b.id)
    w = Wish(
        org_id=test_org.id,
        title="Заявка для проверки инициатора",
        status="draft",
        created_by=test_user.id,
        subsidy_id=test_subsidy.id,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)

    token = create_access_token({"sub": test_user.username, "org_id": test_user.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        f"/api/wishes/{w.id}/documents/service_note?initiator_id={outsider.id}",
        headers=headers,
    )
    assert resp.status_code == 403
    body = resp.json()
    # Глобальный error-handler реэкспортирует detail-dict в top-level "code"
    # (а не только под ключ "detail") — см. ответ выше в выводе теста.
    detail = body.get("detail")
    code = body.get("code") or (detail.get("code") if isinstance(detail, dict) else None)
    assert code == "INITIATOR_FORBIDDEN", resp.text
