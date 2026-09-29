# -*- coding: utf-8 -*-
"""Владелец: «Верхним согласующим необходимости закупки можно ставить только
того, кто имеет право корректировать субсидию. Иначе каждый сотрудник будет
сам себя ставить и сам себе согласовывать».

Уточнение владельца (2026-09-29): единственный критерий — право
'subsidy.edit'. Если автор заявки САМ обладает этим правом, он вправе быть
верхним согласующим и провести всю заявку в одиночку (согласовать сам себя) —
отдельного запрета «автор == согласующий» НЕТ.

Право «корректировать субсидию» — ТА ЖЕ проверка, что у PUT/DELETE субсидии
(has_org_key(..., 'subsidy.edit', subsidy_id=...), см. subsidies.py) —
app/routers/wish_approvals.py::_validate_top_approver переиспользует её, не
заводит вторую (ПРАВИЛО №6). Кандидаты для UI (GET .../approvers/candidates)
переиспользуют тот же расчёт пула, что и согласующие превышения ФЭО
(app.services.authorized_approvers.list_users_with_org_key).

Покрытие:
  1. POST .../approvers/cascade с top_user_id без subsidy.edit -> 400.
  2. POST .../approvers/cascade с top_user_id с subsidy.edit -> 200, цепочка
     построена и оканчивается им.
  3. Автор заявки с subsidy.edit МОЖЕТ быть верхним согласующим (cascade 200)
     и сам согласовать свой единственный шаг (decide 200, заявка approved).
  4. Автор заявки БЕЗ subsidy.edit не может ни назначить себя верхним
     (cascade 400), ни быть назначен вручную единственным согласующим
     (add_wish_approver 400).
  5. GET .../approvers/candidates — не включает сотрудников без subsidy.edit;
     ВКЛЮЧАЕТ автора заявки, если у него это право есть.
"""
import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_approval import WishApproval
from app.models.subsidy import Subsidy


async def _mk_wish(db_session, test_org, author, subsidy=None, status="draft"):
    w = Wish(
        org_id=test_org.id,
        title="Тестовая заявка",
        status=status,
        created_by=author.id,
        subsidy_id=subsidy.id if subsidy else None,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


def _headers_for(user):
    from app.auth.jwt import create_access_token
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_cascade_rejects_top_without_subsidy_edit(
    client, db_session, test_org, make_user, superadmin_headers,
):
    author = await make_user(role="employee", org_id=test_org.id)
    plain_employee = await make_user(role="employee", org_id=test_org.id)
    subsidy = Subsidy(name="Subsidy A", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    w = await _mk_wish(db_session, test_org, author, subsidy=subsidy)

    resp = await client.post(
        f"/api/wishes/{w.id}/approvers/cascade",
        headers=superadmin_headers,
        json={"top_user_id": plain_employee.id},
    )
    assert resp.status_code == 400, resp.text
    assert "правом корректировать субсидию" in resp.json()["message"]

    rows = (await db_session.execute(
        select(WishApproval).where(WishApproval.wish_id == w.id)
    )).scalars().all()
    assert rows == [], "Цепочка не должна была построиться при отказе"


@pytest.mark.asyncio
async def test_cascade_accepts_top_with_subsidy_edit(
    client, db_session, test_org, make_user, superadmin_headers,
):
    author = await make_user(role="employee", org_id=test_org.id)
    # org_admin — по умолчанию имеет subsidy.edit (см. perm_seed_hotfix.sql).
    top_approver = await make_user(role="org_admin", org_id=test_org.id, full_name="Верхний Согласующий")
    subsidy = Subsidy(name="Subsidy B", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    w = await _mk_wish(db_session, test_org, author, subsidy=subsidy)

    resp = await client.post(
        f"/api/wishes/{w.id}/approvers/cascade",
        headers=superadmin_headers,
        json={"top_user_id": top_approver.id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["approvers"], "Цепочка должна содержать хотя бы верхнего согласующего"
    assert body["approvers"][-1]["user_id"] == top_approver.id


@pytest.mark.asyncio
async def test_author_with_subsidy_edit_can_be_top_and_self_approve(
    client, db_session, test_org, make_user, superadmin_headers,
):
    """Уточнение владельца: автор с правом subsidy.edit МОЖЕТ провести всю
    заявку в одиночку — назначить себя верхним согласующим и сам согласовать
    свой единственный шаг."""
    author = await make_user(role="org_admin", org_id=test_org.id)
    subsidy = Subsidy(name="Subsidy C", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    w = await _mk_wish(db_session, test_org, author, subsidy=subsidy)

    resp = await client.post(
        f"/api/wishes/{w.id}/approvers/cascade",
        headers=superadmin_headers,
        json={"top_user_id": author.id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["approvers"]
    assert body["approvers"][-1]["user_id"] == author.id
    approval_id = body["approvers"][-1]["id"]

    # Заявка должна быть submitted, чтобы decide прошёл гейт статуса.
    w.status = "submitted"
    await db_session.commit()

    decide_resp = await client.post(
        f"/api/wishes/{w.id}/approvers/{approval_id}/decide",
        headers=_headers_for(author),
        json={"decision": "approved"},
    )
    assert decide_resp.status_code == 200, decide_resp.text


@pytest.mark.asyncio
async def test_author_without_subsidy_edit_cannot_be_top_via_cascade(
    client, db_session, test_org, make_user, superadmin_headers,
):
    author = await make_user(role="employee", org_id=test_org.id)
    subsidy = Subsidy(name="Subsidy D", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    w = await _mk_wish(db_session, test_org, author, subsidy=subsidy)

    resp = await client.post(
        f"/api/wishes/{w.id}/approvers/cascade",
        headers=superadmin_headers,
        json={"top_user_id": author.id},
    )
    assert resp.status_code == 400, resp.text
    assert "правом корректировать субсидию" in resp.json()["message"]


@pytest.mark.asyncio
async def test_author_without_subsidy_edit_cannot_self_add_as_sole_approver(
    client, db_session, test_org, make_user, superadmin_headers,
):
    """POST /approvers (ручное назначение, без кнопки «Построить цепочку») —
    прямой аналог top_user_id, когда это ЕДИНСТВЕННЫЙ согласующий."""
    author = await make_user(role="employee", org_id=test_org.id)
    subsidy = Subsidy(name="Subsidy E", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    w = await _mk_wish(db_session, test_org, author, subsidy=subsidy)

    resp = await client.post(
        f"/api/wishes/{w.id}/approvers",
        headers=superadmin_headers,
        json={"user_id": author.id},
    )
    assert resp.status_code == 400, resp.text
    assert "правом корректировать субсидию" in resp.json()["message"]


@pytest.mark.asyncio
async def test_candidates_endpoint_includes_author_when_authorized(
    client, db_session, test_org, make_user, superadmin_headers,
):
    author = await make_user(role="org_admin", org_id=test_org.id)
    plain_employee = await make_user(role="employee", org_id=test_org.id)
    subsidy = Subsidy(name="Subsidy F", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    # Кандидатов собираем по членству (UserOrganization/UserOrgAccess) — как
    # реальные сотрудники организации, а не по глобальному User.org_id
    # (см. app.services.authorized_approvers.list_users_with_org_key).
    from app.models.user_organization import UserOrganization
    db_session.add_all([
        UserOrganization(user_id=author.id, org_id=test_org.id),
        UserOrganization(user_id=plain_employee.id, org_id=test_org.id),
    ])
    await db_session.commit()

    w = await _mk_wish(db_session, test_org, author, subsidy=subsidy)

    resp = await client.get(
        f"/api/wishes/{w.id}/approvers/candidates", headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    assert author.id in ids, "Автор с subsidy.edit обязан быть в списке кандидатов"
    assert plain_employee.id not in ids
