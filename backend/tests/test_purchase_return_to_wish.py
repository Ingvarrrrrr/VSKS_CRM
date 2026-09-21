"""POST/GET /api/purchases/{id}/return-to-wish[/preview] (routers/purchase_return.py).

Владелец 21.09, corrections-21-09.md W3: третий вариант работы с дублями
строк ТЗ — «ошибка, вернуть на доработку». Проверяет: статусы/approval_status
закупки сброшены, заявка ушла в rejected с комментарием, PurchaseApproval
удалены (переиспользует services/purchase_approval_reset.py), 409 без wish_id
и на неподходящей стадии.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.purchase import Purchase
from app.models.purchase_approval import PurchaseApproval
from app.models.wish import Wish
from app.models.wish_approval import WishApproval


async def _make_wish(db_session, test_org, test_user) -> Wish:
    w = Wish(
        org_id=test_org.id,
        title="Заявка для возврата 21.09",
        status="converted",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


async def _make_purchase(db_session, wish: Wish, status="plan_schedule") -> Purchase:
    p = Purchase(
        status=status, item_type="goods", item_name="Закупка для возврата",
        wish_id=wish.id, approval_status="in_progress",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_preview_allowed_for_plan_schedule(client, db_session, test_org, test_user, admin_headers):
    wish = await _make_wish(db_session, test_org, test_user)
    p = await _make_purchase(db_session, wish, status="plan_schedule")
    resp = await client.get(f"/api/purchases/{p.id}/return-to-wish/preview", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["allowed"] is True
    assert body["reason"] is None
    assert len(body["consequences"]) >= 1


@pytest.mark.asyncio
async def test_preview_blocked_without_wish(client, db_session, admin_headers):
    p = Purchase(status="plan_schedule", item_type="goods", item_name="Без заявки")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    resp = await client.get(f"/api/purchases/{p.id}/return-to-wish/preview", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is False
    assert "заявк" in body["reason"].lower()


@pytest.mark.asyncio
async def test_preview_blocked_for_disallowed_status(client, db_session, test_org, test_user, admin_headers):
    wish = await _make_wish(db_session, test_org, test_user)
    p = await _make_purchase(db_session, wish, status="contracted")
    resp = await client.get(f"/api/purchases/{p.id}/return-to-wish/preview", headers=admin_headers)
    body = resp.json()
    assert body["allowed"] is False
    assert "Заключён договор" in body["reason"]


@pytest.mark.asyncio
async def test_return_to_wish_resets_status_and_rejects_wish(
    client, db_session, test_org, test_user, test_admin_user, admin_headers,
):
    wish = await _make_wish(db_session, test_org, test_user)
    p = await _make_purchase(db_session, wish, status="work_in_progress")

    # Живой шаг согласования закупки — должен быть удалён.
    db_session.add(PurchaseApproval(
        purchase_id=p.id, order_num=0, role_name="Руководитель",
        approver_full_name="Тестовый Согласующий", status="pending",
    ))
    # Живой шаг согласования заявки — должен вернуться в pending (как при
    # обычном отклонении заявки, см. wish_transitions.py::reject_wish).
    db_session.add(WishApproval(
        wish_id=wish.id, order_num=0, role_name="Руководитель",
        approver_full_name="Тестовый Согласующий", status="approved",
    ))
    await db_session.commit()

    resp = await client.post(
        f"/api/purchases/{p.id}/return-to-wish",
        json={"comment": "Обнаружены дубли ТЗ, нужна доработка"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purchase_status"] == "wishes"
    assert body["wish_status"] == "rejected"

    await db_session.refresh(p)
    assert p.status == "wishes"
    assert p.approval_status is None

    await db_session.refresh(wish)
    assert wish.status == "rejected"
    assert wish.rejection_reason == "Обнаружены дубли ТЗ, нужна доработка"
    assert wish.rejected_by == test_admin_user.id

    remaining_pa = (await db_session.execute(
        select(PurchaseApproval).where(PurchaseApproval.purchase_id == p.id)
    )).scalars().all()
    assert remaining_pa == []

    wa = (await db_session.execute(
        select(WishApproval).where(WishApproval.wish_id == wish.id)
    )).scalars().all()
    assert len(wa) == 1
    assert wa[0].status == "pending"


@pytest.mark.asyncio
async def test_return_to_wish_409_without_wish_id(client, db_session, admin_headers):
    p = Purchase(status="plan_schedule", item_type="goods", item_name="Без заявки 2")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    resp = await client.post(
        f"/api/purchases/{p.id}/return-to-wish",
        json={"comment": "тест"},
        headers=admin_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_return_to_wish_409_for_disallowed_status(client, db_session, test_org, test_user, admin_headers):
    wish = await _make_wish(db_session, test_org, test_user)
    p = await _make_purchase(db_session, wish, status="delivered")
    resp = await client.post(
        f"/api/purchases/{p.id}/return-to-wish",
        json={"comment": "тест"},
        headers=admin_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_return_to_wish_requires_permission_for_plain_employee(
    client, db_session, test_org, test_user, auth_headers,
):
    """employee без роли manager+ и без permission action 'purchase.status_change' → 403
    (тот же гейт, что и у POST /purchases/{id}/transition)."""
    wish = await _make_wish(db_session, test_org, test_user)
    p = await _make_purchase(db_session, wish, status="plan_schedule")
    resp = await client.post(
        f"/api/purchases/{p.id}/return-to-wish",
        json={"comment": "тест"},
        headers=auth_headers,
    )
    assert resp.status_code == 403
