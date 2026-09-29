# -*- coding: utf-8 -*-
"""Авансовый не должен уходить в план закупок без согласования возмещения
(владелец, 2026-09-29): «алгоритм везде один: авансовый создан — сначала на
согласование, иначе все сотрудники наделают авансовых и оставят их в плане
закупок». Для обычной закупки из заявки закупка появляется только ПОСЛЕ
согласования заявки (app/routers/wish_convert.py::convert_wish); для
авансового — тот же принцип реализован в app/routers/purchase_transitions.py
::transition_status: первый выход из status='wishes' запрещён, пока
companion-заявка (Purchase.wish_id, source='advance_report') не в статусе
'approved' либо 'converted' (реальный терминал полного согласования — см.
app/routers/wish_approvals.py::decide, companion всегда имеет WishItem-и и
поэтому проходит approved -> converted в одной транзакции).
"""
import pytest

from app.models.wish import Wish


async def _create_advance_purchase(client, auth_headers, price=500):
    payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест гейта",
        "items": [
            {
                "item_name": "Такси",
                "item_type": "услуга",
                "quantity": 1,
                "unit": "шт",
                "unit_price": price,
                "total_price": price,
            }
        ],
    }
    resp = await client.post("/api/purchases/", json=payload, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_advance_transition_to_plan_blocked_while_companion_draft(
    client, auth_headers, admin_headers, db_session,
):
    data = await _create_advance_purchase(client, auth_headers)
    purchase_id = data["id"]
    wish_id = data["wish_id"]

    wish = await db_session.get(Wish, wish_id)
    assert wish.status == "draft"

    resp = await client.post(
        f"/api/purchases/{purchase_id}/transition?status=plan_schedule",
        headers=admin_headers,
    )
    assert resp.status_code == 409, resp.text
    message = (resp.json().get("message") or resp.json().get("detail") or "")
    assert "согласован" in message.lower()


@pytest.mark.asyncio
async def test_advance_transition_to_plan_allowed_once_companion_approved(
    client, auth_headers, admin_headers, db_session,
):
    data = await _create_advance_purchase(client, auth_headers)
    purchase_id = data["id"]
    wish_id = data["wish_id"]

    wish = await db_session.get(Wish, wish_id)
    wish.status = "approved"
    db_session.add(wish)
    await db_session.commit()

    resp = await client.post(
        f"/api/purchases/{purchase_id}/transition?status=plan_schedule",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "plan_schedule"


@pytest.mark.asyncio
async def test_advance_transition_to_plan_allowed_once_companion_converted(
    client, auth_headers, admin_headers, db_session,
):
    """'converted' — реальный терминал после полного согласования (не 'approved',
    см. докстринг модуля) — тоже должен пропускать переход."""
    data = await _create_advance_purchase(client, auth_headers)
    purchase_id = data["id"]
    wish_id = data["wish_id"]

    wish = await db_session.get(Wish, wish_id)
    wish.status = "converted"
    db_session.add(wish)
    await db_session.commit()

    resp = await client.post(
        f"/api/purchases/{purchase_id}/transition?status=plan_schedule",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
