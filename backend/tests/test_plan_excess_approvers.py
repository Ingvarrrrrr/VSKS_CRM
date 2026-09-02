"""Регрессия (владелец продукта, 2026-09-02): «АНО ЦЕНТРПОИСК» — все 7
участников организации employee, никому право plan_excess.decide не
положено, а владелец организации (Organization.owner_user_id, роль
account_owner) не числился УЧАСТНИКОМ этой организации — пул кандидатов в
_authorized_plan_excess_approvers (app/routers/plan_excess.py) был пуст, и
пользователю выдавалось «согласовать некому», хотя фактически согласующий
(владелец) существует.

Фикс: четвёртый источник кандидатов — Organization.owner_user_id для org_id
запроса. has_org_key пропускает account_owner/superadmin без проверки
org_id (см. app/auth/permissions.py::has_org_key), так что владелец
организации автоматически проходит отбор, если он попал в пул кандидатов.
"""
import pytest

from app.models.organization import Organization
from app.routers.plan_excess import _authorized_plan_excess_approvers


@pytest.mark.asyncio
async def test_org_owner_not_member_becomes_approver_when_no_one_else_authorized(
    db_session, make_user,
):
    """Ключевой сценарий из бага: организация, где ни один УЧАСТНИК не имеет
    права plan_excess.decide (все employee), но есть владелец организации
    (Organization.owner_user_id) с ролью account_owner, сам НЕ являющийся
    участником организации (не в UserOrganization/UserOrgAccess). Список
    согласующих не должен быть пуст и обязан содержать владельца."""
    owner = await make_user(role="account_owner")

    org = Organization(name="Owner_Not_Member_Org", owner_user_id=owner.id)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    # Обычные сотрудники организации — без права, ни один не должен
    # оказаться в approvers (это часть исходного бага-репродукции).
    await make_user(role="employee", org_id=org.id)
    await make_user(role="employee", org_id=org.id)

    approvers = await _authorized_plan_excess_approvers(
        db_session, org.id, subsidy_id=999999,
    )

    assert approvers, "Список согласующих не должен быть пуст — владелец организации обязан в нём быть"
    approver_ids = {u.id for u in approvers}
    assert owner.id in approver_ids


@pytest.mark.asyncio
async def test_org_without_owner_and_without_authorized_members_has_no_approvers(
    db_session, test_org, make_user,
):
    """Guard: если у организации нет owner_user_id и ни один участник не
    авторизован — approvers пуст, как и раньше (не плодим ложных
    согласующих там, где их действительно нет)."""
    assert test_org.owner_user_id is None  # test_org фикстура не задаёт владельца

    await make_user(role="employee", org_id=test_org.id)

    approvers = await _authorized_plan_excess_approvers(
        db_session, test_org.id, subsidy_id=999999,
    )
    assert approvers == []


@pytest.mark.asyncio
async def test_org_owner_excluded_when_he_is_the_requester(db_session, make_user):
    """Самосогласование запрещено: если запрос подаёт сам владелец
    организации, он не должен оказаться в списке согласующих своего же
    запроса (exclude_user_id), даже если он — единственный кандидат."""
    owner = await make_user(role="account_owner")

    org = Organization(name="Owner_Self_Request_Org", owner_user_id=owner.id)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    approvers = await _authorized_plan_excess_approvers(
        db_session, org.id, subsidy_id=999999, exclude_user_id=owner.id,
    )
    assert approvers == []
