# -*- coding: utf-8 -*-
"""Владелец: «Согласующих можно менять местами только при последовательном
согласовании». POST /wishes/{id}/approvers/reorder должен отклонять запрос
409-м, если wish.approval_mode == 'parallel', и разрешать при 'sequential'
(app/routers/wish_approvals.py::reorder_wish_approvers).
"""
import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_approval import WishApproval
from app.models.subsidy import Subsidy


async def _mk_wish_with_two_approvers(db_session, test_org, make_user, client, superadmin_headers, mode):
    author = await make_user(role="employee", org_id=test_org.id)
    top_approver = await make_user(role="org_admin", org_id=test_org.id, full_name="Верхний")
    second_approver = await make_user(role="employee", org_id=test_org.id, full_name="Второй")
    subsidy = Subsidy(name=f"Subsidy reorder {mode}", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    w = Wish(
        org_id=test_org.id,
        title="Тестовая заявка",
        status="draft",
        created_by=author.id,
        subsidy_id=subsidy.id,
        approval_mode=mode,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)

    # Первый согласующий проходит проверку subsidy.edit (max_order is None).
    resp = await client.post(
        f"/api/wishes/{w.id}/approvers",
        headers=superadmin_headers,
        json={"user_id": top_approver.id},
    )
    assert resp.status_code == 201, resp.text
    # Второй — без проверки (order уже занят).
    resp = await client.post(
        f"/api/wishes/{w.id}/approvers",
        headers=superadmin_headers,
        json={"user_id": second_approver.id},
    )
    assert resp.status_code == 201, resp.text

    rows = (await db_session.execute(
        select(WishApproval).where(WishApproval.wish_id == w.id).order_by(WishApproval.order_num)
    )).scalars().all()
    assert len(rows) == 2
    return w, rows


@pytest.mark.asyncio
async def test_reorder_rejected_when_parallel(
    client, db_session, test_org, make_user, superadmin_headers,
):
    w, rows = await _mk_wish_with_two_approvers(
        db_session, test_org, make_user, client, superadmin_headers, mode="parallel",
    )
    ids_swapped = [rows[1].id, rows[0].id]

    resp = await client.post(
        f"/api/wishes/{w.id}/approvers/reorder",
        headers=superadmin_headers,
        json={"ids": ids_swapped},
    )
    assert resp.status_code == 409, resp.text
    assert "последовательном согласовании" in resp.json()["message"]

    # Порядок в БД не должен был измениться.
    fresh = (await db_session.execute(
        select(WishApproval).where(WishApproval.wish_id == w.id).order_by(WishApproval.order_num)
    )).scalars().all()
    assert [r.id for r in fresh] == [rows[0].id, rows[1].id]


@pytest.mark.asyncio
async def test_reorder_allowed_when_sequential(
    client, db_session, test_org, make_user, superadmin_headers,
):
    w, rows = await _mk_wish_with_two_approvers(
        db_session, test_org, make_user, client, superadmin_headers, mode="sequential",
    )
    ids_swapped = [rows[1].id, rows[0].id]

    resp = await client.post(
        f"/api/wishes/{w.id}/approvers/reorder",
        headers=superadmin_headers,
        json={"ids": ids_swapped},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [a["id"] for a in body] == ids_swapped
