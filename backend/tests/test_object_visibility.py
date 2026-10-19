# -*- coding: utf-8 -*-
"""Тесты для app.auth.object_visibility (исправление К2, 19.10.2026): «видимость
объекта по id = видимость в списке». До этой правки GET /api/purchases/{id},
GET /api/tasks/{id}, .../comments, файлы закупки и документы открывались по id
БЕЗ единой проверки видимости — поведенческое тестирование (tests/behavior/
REPORT.md, находки К1/К2) подтвердило это вручную на bt-стенде: сотрудник
другой организации и владелец ДРУГОГО аккаунта читали чужую закупку/задачу/
файл/ТЗ по известному id, хотя сама субсидия/задача им не видна в списке.

Также покрывает К1 (account_owner ограничен контуром СВОЕГО аккаунта, не всех
аккаунтов — app/auth/visibility.py::compute_account_contour_org_ids, jwt.py::
get_org_filter) и легитимные случаи, которые нельзя было сломать: руководитель
видит закупку/задачу подчинённого (только чтение), согласующий видит заявку.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.auth.object_visibility import (
    ensure_purchase_visible,
    ensure_task_visible,
    ensure_subsidy_visible,
    ensure_wish_visible,
)


async def _make_org(db_session, owner_user_id=None, root_org_id=None):
    from app.models.contractor import Contractor
    from app.models.organization import Organization
    name = f"ObjVisOrg-{uuid.uuid4().hex[:8]}"
    contractor = Contractor(name=name)
    db_session.add(contractor)
    await db_session.flush()
    org = Organization(contractor_id=contractor.id, owner_user_id=owner_user_id, root_org_id=root_org_id)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


async def _make_subsidy(db_session, org_id):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"ObjVisSubsidy-{uuid.uuid4().hex[:8]}", year=2026, org_id=org_id, status="approved")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_task(db_session, created_by_id=None, assigned_user_id=None, org_id=None):
    from app.models.task import Task
    t = Task(title=f"ObjVisTask-{uuid.uuid4().hex[:8]}", created_by_id=created_by_id,
              assigned_user_id=assigned_user_id, org_id=org_id)
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


# ---------------------------------------------------------------------------
# К1: account_owner ограничен контуром своего аккаунта
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_account_owner_does_not_see_purchase_of_foreign_account(db_session, make_purchase, make_user):
    """Хозяин аккаунта Б не видит закупку аккаунта А по id (раньше account_owner
    был в _SAAS_ROLES = глобальный bypass без ограничения по аккаунту)."""
    org_a = await _make_org(db_session)
    owner_b_org = await _make_org(db_session)
    owner_b = await make_user(role="account_owner", org_id=owner_b_org.id)
    owner_b_org.owner_user_id = owner_b.id
    await db_session.commit()

    subsidy_a = await _make_subsidy(db_session, org_a.id)
    purchase = await make_purchase(status="planned", subsidy_id=subsidy_a.id)

    with pytest.raises(HTTPException) as exc_info:
        await ensure_purchase_visible(owner_b, purchase.id, db_session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_account_owner_does_not_see_task_of_foreign_account(db_session, make_user):
    org_a = await _make_org(db_session)
    employee_a = await make_user(role="employee", org_id=org_a.id)
    task = await _make_task(db_session, created_by_id=employee_a.id, org_id=org_a.id)

    owner_b_org = await _make_org(db_session)
    owner_b = await make_user(role="account_owner", org_id=owner_b_org.id)
    owner_b_org.owner_user_id = owner_b.id
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await ensure_task_visible(owner_b, task.id, db_session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_account_owner_does_not_see_subsidy_of_foreign_account(db_session, make_user):
    org_a = await _make_org(db_session)
    subsidy_a = await _make_subsidy(db_session, org_a.id)

    owner_b_org = await _make_org(db_session)
    owner_b = await make_user(role="account_owner", org_id=owner_b_org.id)
    owner_b_org.owner_user_id = owner_b.id
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await ensure_subsidy_visible(owner_b, subsidy_a.id, db_session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_account_owner_sees_subsidy_in_own_account(db_session, make_user):
    """Контроль: хозяин ВИДИТ субсидию СВОЕЙ организации (контур = своя корневая
    орга + дочерние) — правка К1 не должна была сломать легитимный доступ."""
    owner_org = await _make_org(db_session)
    owner = await make_user(role="account_owner", org_id=owner_org.id)
    owner_org.owner_user_id = owner.id
    await db_session.commit()

    subsidy = await _make_subsidy(db_session, owner_org.id)
    result = await ensure_subsidy_visible(owner, subsidy.id, db_session)
    assert result.id == subsidy.id


# ---------------------------------------------------------------------------
# К2: сотрудник другой организации того же аккаунта не видит объект по id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_employee_of_other_org_does_not_see_purchase(db_session, make_purchase, make_user, test_org):
    """Сотрудник орг. A2 не видит закупку субсидии орг. A1 по id (не назначен,
    не участник, нет вкладки 'purchases' в чужой орге)."""
    org_a1 = test_org
    org_a2 = await _make_org(db_session)
    employee_a2 = await make_user(role="employee", org_id=org_a2.id)

    subsidy_a1 = await _make_subsidy(db_session, org_a1.id)
    purchase = await make_purchase(status="planned", subsidy_id=subsidy_a1.id)

    with pytest.raises(HTTPException) as exc_info:
        await ensure_purchase_visible(employee_a2, purchase.id, db_session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_employee_of_other_org_does_not_see_task(db_session, make_user, test_org):
    org_a1 = test_org
    employee_a1 = await make_user(role="employee", org_id=org_a1.id)
    task = await _make_task(db_session, created_by_id=employee_a1.id, org_id=org_a1.id)

    org_a2 = await _make_org(db_session)
    employee_a2 = await make_user(role="employee", org_id=org_a2.id)

    with pytest.raises(HTTPException) as exc_info:
        await ensure_task_visible(employee_a2, task.id, db_session)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Контроль: легитимный доступ НЕ должен был сломаться
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assignee_sees_own_purchase(db_session, make_purchase, make_user, test_org):
    """Сотрудник, на которого назначена закупка (assigned_user_id), видит её по
    id — build_visibility_clause('purchase') матчит assigned_user_id ∈
    visible_uids (visible всегда включает самого пользователя)."""
    employee = await make_user(role="employee", org_id=test_org.id)
    subsidy = await _make_subsidy(db_session, test_org.id)
    purchase = await make_purchase(status="planned", subsidy_id=subsidy.id, assigned_user_id=employee.id)

    result = await ensure_purchase_visible(employee, purchase.id, db_session)
    assert result.id == purchase.id


@pytest.mark.asyncio
async def test_manager_sees_subordinate_task_read_only(db_session, make_user, test_org):
    """Руководитель видит ЗАДАЧУ подчинённого (создана подчинённым) — иерархия
    даёт READ (get_visible_user_ids → build_visibility_clause('task')
    Task.created_by_id.in_(visible_uids)), запись по-прежнему по своим правам
    (не проверяется этим хелпером — ensure_task_visible только про READ)."""
    from app.models.user_hierarchy import UserHierarchy
    manager = await make_user(role="manager", org_id=test_org.id)
    subordinate = await make_user(role="employee", org_id=test_org.id)
    db_session.add(UserHierarchy(manager_id=manager.id, subordinate_id=subordinate.id))
    await db_session.commit()

    task = await _make_task(db_session, created_by_id=subordinate.id, org_id=test_org.id)

    result = await ensure_task_visible(manager, task.id, db_session)
    assert result.id == task.id


@pytest.mark.asyncio
async def test_wish_approver_sees_wish(db_session, make_user, test_org):
    """Согласующий из цепочки WishApproval видит заявку (ensure_wish_visible
    переиспользует services.wish_access.ensure_wish_read_access — единственный
    источник, тот же что GET /api/wishes/{id})."""
    from app.models.wish import Wish
    from app.models.wish_approval import WishApproval

    creator = await make_user(role="employee", org_id=test_org.id)
    approver = await make_user(role="employee", org_id=test_org.id)

    wish = Wish(org_id=test_org.id, title="ObjVis wish", status="pending_approval", created_by=creator.id)
    db_session.add(wish)
    await db_session.flush()
    db_session.add(WishApproval(wish_id=wish.id, user_id=approver.id, order_num=0, status="pending"))
    await db_session.commit()
    await db_session.refresh(wish)

    result = await ensure_wish_visible(approver, wish.id, db_session)
    assert result.id == wish.id


@pytest.mark.asyncio
async def test_purchase_approver_sees_purchase_without_hierarchy_or_subsidy_access(
    db_session, make_purchase, make_user,
):
    """QA-итерация 2 (регрессия, 19.10.2026): добавление PurchaseApproval.user_id
    в правило видимости закупки (app/auth/visibility.py::
    _purchase_participation_clauses) не должно было отнять видимость у
    согласующего — проверяем прямо противоположный случай: согласующий из
    ДРУГОЙ организации ТОГО ЖЕ аккаунта, без иерархии и без доступа к
    субсидии, видит закупку по id, потому что стоит в её листе согласования."""
    from app.models.purchase_approval import PurchaseApproval

    org_a1 = await _make_org(db_session)
    org_a2 = await _make_org(db_session)
    approver = await make_user(role="employee", org_id=org_a2.id)

    subsidy = await _make_subsidy(db_session, org_a1.id)
    purchase = await make_purchase(status="planned", subsidy_id=subsidy.id)

    db_session.add(PurchaseApproval(
        purchase_id=purchase.id, user_id=approver.id,
        order_num=0, role_name="Согласующий", approver_full_name="Test Approver",
    ))
    await db_session.commit()

    result = await ensure_purchase_visible(approver, purchase.id, db_session)
    assert result.id == purchase.id


@pytest.mark.asyncio
async def test_wish_approval_chain_approver_sees_purchase_created_from_wish(
    db_session, make_purchase, make_user, test_org,
):
    """Согласующий ЗАЯВКИ, из которой создана закупка (Purchase.wish_id),
    тоже видит закупку — WishApproval.user_id в том же правиле."""
    from app.models.wish import Wish
    from app.models.wish_approval import WishApproval

    org_other = await _make_org(db_session)
    approver = await make_user(role="employee", org_id=org_other.id)
    creator = await make_user(role="employee", org_id=test_org.id)

    wish = Wish(org_id=test_org.id, title="ObjVis wish for purchase", status="converted", created_by=creator.id)
    db_session.add(wish)
    await db_session.flush()
    db_session.add(WishApproval(wish_id=wish.id, user_id=approver.id, order_num=0, status="approved"))
    await db_session.commit()
    await db_session.refresh(wish)

    subsidy = await _make_subsidy(db_session, test_org.id)
    purchase = await make_purchase(status="planned", subsidy_id=subsidy.id, wish_id=wish.id)

    result = await ensure_purchase_visible(approver, purchase.id, db_session)
    assert result.id == purchase.id


@pytest.mark.asyncio
async def test_superadmin_sees_everything(db_session, make_purchase, make_user, superadmin_user):
    """Контроль: superadmin — настоящий SaaS bypass, не ограничен ни одним
    контуром (в отличие от account_owner после правки К1)."""
    org = await _make_org(db_session)
    subsidy = await _make_subsidy(db_session, org.id)
    purchase = await make_purchase(status="planned", subsidy_id=subsidy.id)

    result = await ensure_purchase_visible(superadmin_user, purchase.id, db_session)
    assert result.id == purchase.id
