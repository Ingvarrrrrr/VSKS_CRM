# -*- coding: utf-8 -*-
"""Владелец (22.10.2026): «В согласование необходимости закупки можно вообще
кого угодно включить, а корректировка сумм — только у тех, у кого галочки».

Согласующим заявки (верхним и любым другим в цепочке) может быть ЛЮБОЙ
пользователь аккаунта — без проверки конкретных прав (wish.approve/
subsidy.edit относятся к деньгам, не к согласованию необходимости закупки).
Единственная серверная проверка — пользователь должен быть из того же
аккаунта (контура), что и организация заявки — app.services.
wish_approver_pool.assert_approver_in_pool/approver_pool_user_ids.

Покрытие:
  1. Сотрудник без каких-либо прав — в кандидатах, проходит cascade и add.
  2. Пользователь ЧУЖОГО аккаунта → 400 и в cascade, и в add (любая позиция,
     не только первая).
  3. GET /approvers/candidates отдаёт весь пул, отсортированный по ФИО.
  4. Цепочка «к произвольному согласующему» (POST .../{approval_id}/chain):
     top — реальный начальник автора → промежуточные звенья добавляются;
     top не начальник автора → только он, с предупреждением, без дублей.
"""
import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_approval import WishApproval
from app.models.subsidy import Subsidy
from app.models.organization import Organization


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
async def test_plain_employee_without_any_permission_is_candidate_and_passes_cascade(
    client, db_session, test_org, make_user, superadmin_headers,
):
    author = await make_user(role="employee", org_id=test_org.id)
    plain_employee = await make_user(role="employee", org_id=test_org.id, full_name="Рядовой Сотрудник")
    subsidy = Subsidy(name="Subsidy A", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    w = await _mk_wish(db_session, test_org, author, subsidy=subsidy)

    candidates_resp = await client.get(
        f"/api/wishes/{w.id}/approvers/candidates", headers=superadmin_headers,
    )
    assert candidates_resp.status_code == 200, candidates_resp.text
    ids = {row["id"] for row in candidates_resp.json()}
    assert plain_employee.id in ids, "Рядовой сотрудник без прав обязан быть кандидатом"

    resp = await client.post(
        f"/api/wishes/{w.id}/approvers/cascade",
        headers=superadmin_headers,
        json={"top_user_id": plain_employee.id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["approvers"][-1]["user_id"] == plain_employee.id


@pytest.mark.asyncio
async def test_outsider_rejected_in_cascade_and_in_manual_add_any_position(
    client, db_session, test_org, make_user, superadmin_headers,
):
    """Пользователь другого, никак не связанного аккаунта — не кандидат,
    400 и в cascade (верхний), и в add (И первым, И вторым согласующим —
    дыра была именно в том, что любая позиция кроме первой не проверялась)."""
    author = await make_user(role="employee", org_id=test_org.id)
    insider = await make_user(role="employee", org_id=test_org.id, full_name="Свой")

    other_org = Organization(name="Чужой аккаунт")
    db_session.add(other_org)
    await db_session.commit()
    await db_session.refresh(other_org)
    outsider = await make_user(role="employee", org_id=other_org.id, full_name="Чужой")

    subsidy = Subsidy(name="Subsidy B", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    w = await _mk_wish(db_session, test_org, author, subsidy=subsidy)

    # Верхний (cascade) — чужой аккаунт отклоняется.
    resp = await client.post(
        f"/api/wishes/{w.id}/approvers/cascade",
        headers=superadmin_headers,
        json={"top_user_id": outsider.id},
    )
    assert resp.status_code == 400, resp.text
    assert "аккаунта" in resp.json()["message"]
    rows = (await db_session.execute(
        select(WishApproval).where(WishApproval.wish_id == w.id)
    )).scalars().all()
    assert rows == []

    # Первый согласующий вручную — свой, проходит.
    resp = await client.post(
        f"/api/wishes/{w.id}/approvers",
        headers=superadmin_headers,
        json={"user_id": insider.id},
    )
    assert resp.status_code == 201, resp.text

    # ВТОРОЙ согласующий — чужой аккаунт — обязан отклоняться ТОЖЕ, не только
    # первый (дыра до фикса: проверка была только при max_order is None).
    resp = await client.post(
        f"/api/wishes/{w.id}/approvers",
        headers=superadmin_headers,
        json={"user_id": outsider.id},
    )
    assert resp.status_code == 400, resp.text
    assert "аккаунта" in resp.json()["message"]
    rows = (await db_session.execute(
        select(WishApproval).where(WishApproval.wish_id == w.id)
    )).scalars().all()
    assert len(rows) == 1, "Чужой согласующий не должен был добавиться"


@pytest.mark.asyncio
async def test_candidates_sorted_by_full_name(
    client, db_session, test_org, make_user, superadmin_headers,
):
    author = await make_user(role="employee", org_id=test_org.id, full_name="Автор Автор")
    await make_user(role="employee", org_id=test_org.id, full_name="Яковлев Я.Я.")
    await make_user(role="employee", org_id=test_org.id, full_name="Антонов А.А.")
    w = await _mk_wish(db_session, test_org, author)

    resp = await client.get(
        f"/api/wishes/{w.id}/approvers/candidates", headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    names = [row["full_name"] for row in resp.json()]
    assert names == sorted(names, key=str.lower)


@pytest.mark.asyncio
async def test_chain_to_arbitrary_approver_inserts_intermediate_links(
    client, db_session, test_org, make_user, superadmin_headers,
):
    """top — реальный вышестоящий начальник автора (через User.superior_user_id,
    override реального подчинения) → цепочка добавляет промежуточное звено
    между автором и top."""
    top = await make_user(role="manager", org_id=test_org.id, full_name="Директор Директорович")
    middle = await make_user(role="manager", org_id=test_org.id, full_name="Начальник Начальникович",
                              superior_user_id=top.id)
    author = await make_user(role="employee", org_id=test_org.id, full_name="Сотрудник Сотрудникович",
                              superior_user_id=middle.id)

    w = await _mk_wish(db_session, test_org, author)

    # top добавлен вручную (как единственный согласующий, без цепочки).
    add_resp = await client.post(
        f"/api/wishes/{w.id}/approvers",
        headers=superadmin_headers,
        json={"user_id": top.id},
    )
    assert add_resp.status_code == 201, add_resp.text
    approval_id = add_resp.json()["id"]

    chain_resp = await client.post(
        f"/api/wishes/{w.id}/approvers/{approval_id}/chain",
        headers=superadmin_headers,
    )
    assert chain_resp.status_code == 200, chain_resp.text
    body = chain_resp.json()
    approvers = body["approvers"]
    user_ids_in_order = [a["user_id"] for a in approvers]
    assert middle.id in user_ids_in_order, "Промежуточное звено обязано появиться"
    assert top.id in user_ids_in_order
    assert user_ids_in_order.index(middle.id) < user_ids_in_order.index(top.id), \
        "Подчинённый обязан идти раньше начальника в очереди согласования"
    assert author.id not in user_ids_in_order
    # Без дублей top.
    assert user_ids_in_order.count(top.id) == 1


@pytest.mark.asyncio
async def test_chain_to_approver_not_a_superior_returns_warning_without_links(
    client, db_session, test_org, make_user, superadmin_headers,
):
    """top НЕ является начальником автора ни по одной связи — цепочка не
    достраивается молча, сервер возвращает явное предупреждение."""
    author = await make_user(role="employee", org_id=test_org.id, full_name="Автор Автор")
    unrelated_top = await make_user(role="manager", org_id=test_org.id, full_name="Посторонний Посторонний")

    w = await _mk_wish(db_session, test_org, author)

    add_resp = await client.post(
        f"/api/wishes/{w.id}/approvers",
        headers=superadmin_headers,
        json={"user_id": unrelated_top.id},
    )
    assert add_resp.status_code == 201, add_resp.text
    approval_id = add_resp.json()["id"]

    chain_resp = await client.post(
        f"/api/wishes/{w.id}/approvers/{approval_id}/chain",
        headers=superadmin_headers,
    )
    assert chain_resp.status_code == 200, chain_resp.text
    body = chain_resp.json()
    assert body["warning"], "Обязано быть предупреждение — автор не в подчинении у top"
    assert "не в подчинении" in body["warning"]
    rows = (await db_session.execute(
        select(WishApproval).where(WishApproval.wish_id == w.id)
    )).scalars().all()
    assert len(rows) == 1, "Без реального подчинения промежуточные звенья не добавляются"
