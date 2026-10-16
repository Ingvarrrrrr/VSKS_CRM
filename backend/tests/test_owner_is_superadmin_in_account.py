# -*- coding: utf-8 -*-
"""Задача владельца (16.10.2026): «для своего аккаунта владелец и является
суперадмином» — ~58 проверок role=='superadmin'/!='superadmin' в роутерах
разобраны: действия ВНУТРИ аккаунта теперь пускают и account_owner (см.
OWNER_ROLES, app/auth/jwt.py), действия НАД ПЛАТФОРМОЙ (чужие аккаунты,
создание аккаунтов) остались только для superadmin.

Эти два эндпоинта — представительная пара:
  1. app/routers/vehicle_attachments.py::_check_visibility — хозяин аккаунта
     видит вложение ТС своей организации БЕЗ отдельного права (как superadmin
     внутри своего контура), но НЕ видит вложение ТС чужого аккаунта (в
     отличие от superadmin, который видит всё, account_owner — только свой
     аккаунт, см. app/auth/visibility.py::is_org_in_owner_account).
  2. app/routers/feo_categories.py::_has_feo_action — хозяин аккаунта видит
     денежные поля ФЭО (feo_budget.*) без явного action-ключа, как superadmin.
"""
import pytest

from app.auth.visibility import is_org_in_owner_account
from app.models.vehicle import Vehicle
from app.routers.vehicle_attachments import _check_visibility
from app.routers.feo_categories import _has_feo_action


async def _make_org(db_session, owner_user_id=None):
    import uuid
    from app.models.organization import Organization
    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}", owner_user_id=owner_user_id)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


async def _make_vehicle(db_session, owner_org_id):
    v = Vehicle(owner_org_id=owner_org_id, brand="ГАЗель", model="Next")
    db_session.add(v)
    await db_session.commit()
    await db_session.refresh(v)
    return v


@pytest.mark.asyncio
async def test_account_owner_sees_vehicle_attachment_in_own_account(
    db_session, make_user,
):
    owner = await make_user(role="account_owner")
    my_org = await _make_org(db_session, owner_user_id=owner.id)
    vehicle = await _make_vehicle(db_session, my_org.id)

    # Не падает — хозяин аккаунта видит ТС своей организации без 403.
    await _check_visibility(vehicle, owner, db_session)


@pytest.mark.asyncio
async def test_account_owner_denied_vehicle_attachment_in_foreign_account(
    db_session, make_user,
):
    from fastapi import HTTPException

    owner = await make_user(role="account_owner")
    await _make_org(db_session, owner_user_id=owner.id)  # его собственный аккаунт (не используется ниже)
    foreign_org = await _make_org(db_session, owner_user_id=None)  # чужой/ничейный аккаунт
    foreign_vehicle = await _make_vehicle(db_session, foreign_org.id)

    with pytest.raises(HTTPException) as exc_info:
        await _check_visibility(foreign_vehicle, owner, db_session)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_is_org_in_owner_account_true_for_own_org(db_session, make_user):
    owner = await make_user(role="account_owner")
    org = await _make_org(db_session, owner_user_id=owner.id)
    assert await is_org_in_owner_account(db_session, owner, org.id) is True


@pytest.mark.asyncio
async def test_is_org_in_owner_account_false_for_foreign_org(db_session, make_user):
    owner = await make_user(role="account_owner")
    foreign_org = await _make_org(db_session, owner_user_id=None)
    assert await is_org_in_owner_account(db_session, owner, foreign_org.id) is False


@pytest.mark.asyncio
async def test_account_owner_has_feo_action_like_superadmin(db_session, make_user):
    """feo_categories._has_feo_action — бы режет денежные поля feo_budget.* по
    action-ключу, superadmin — всегда True. Хозяин аккаунта теперь тоже."""
    owner = await make_user(role="account_owner")
    assert await _has_feo_action(owner, db_session, "feo_budget.view_all_levels") is True


@pytest.mark.asyncio
async def test_employee_still_needs_explicit_feo_action_key(db_session, make_user):
    """Контроль: обычный сотрудник без права и без OWNER_ROLES — попадает в
    ветку проверки эффективных прав (не безусловный True), поведение не
    расширилось дальше задачи."""
    employee = await make_user(role="employee")
    result = await _has_feo_action(employee, db_session, "feo_budget.view_all_levels")
    assert result is False
