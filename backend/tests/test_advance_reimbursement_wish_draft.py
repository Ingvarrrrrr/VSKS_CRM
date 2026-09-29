# -*- coding: utf-8 -*-
"""Компаньон авансового отчёта (source='advance_report') создаётся ЧЕРНОВИКОМ,
а не уходит сразу всем руководителям по иерархии (решение владельца, опрос
2026-09-15 — см. backend/app/routers/purchases.py::create_purchase и
app/routers/wish_transitions.py::submit_wish).

Покрытие:
  1. POST /api/purchases/ (purchase_method='advance', без wish_id) → компаньон
     status='draft'.
  2. Отправка БЕЗ согласующих → 409, цепочка САМА не строится (владелец,
     2026-09-29, повторно после прод-инцидента с заявкой №85 — submit
     раньше сам собирал цепочку). Согласующих подбирает только явное
     действие: POST /approvers/cascade («Построить цепочку») или ручное
     добавление — после этого submit проходит.
  3. Повторная отправка уже отправленной заявки → понятная ошибка (не 200).
  4. PUT /api/purchases/{id} авансового в статусе draft по-прежнему
     синхронизирует позиции компаньона (WishItem пересобираются).
"""
import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.wish_approval import WishApproval


async def _create_advance_purchase(client, auth_headers, item_name="Такси до вокзала", price=500):
    payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест",
        "items": [
            {
                "item_name": item_name,
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
async def test_advance_companion_wish_created_as_draft(client, auth_headers, db_session):
    data = await _create_advance_purchase(client, auth_headers)
    wish_id = data["wish_id"]
    assert wish_id is not None

    wish = await db_session.get(Wish, wish_id)
    assert wish is not None
    assert wish.status == "draft"
    assert wish.source == "advance_report"


@pytest.mark.asyncio
async def test_submit_advance_companion_without_approvers_returns_409_no_auto_chain(
    client, auth_headers, db_session, test_org, make_user,
):
    """Прод-инцидент (заявка №85, 2026-09-29): submit сам построил цепочку
    Любарец → Цыганов → Козеев без единого нажатия кнопки. Владелец: «цепочка
    автоматически не выстраивается, только если нажато кнопочкой» — теперь
    submit БЕЗ согласующих отказывает 409 и НЕ создаёт ни одной WishApproval,
    даже если руководитель организации по ЕГРЮЛ прекрасно резолвится."""
    await make_user(
        role="manager", last_name="Козеев", first_name="Евгений", middle_name="Викторович",
    )
    test_org.director_last_name = "Козеев"
    test_org.director_first_name = "Евгений"
    test_org.director_middle_name = "Викторович"
    db_session.add(test_org)
    await db_session.commit()

    data = await _create_advance_purchase(client, auth_headers)
    wish_id = data["wish_id"]

    resp = await client.post(f"/api/wishes/{wish_id}/submit", headers=auth_headers)
    assert resp.status_code == 409, resp.text
    message = resp.json().get("message", "")
    assert "не выбран согласующий" in message
    assert "не выбран согласующий" in message

    approvals = (await db_session.execute(
        select(WishApproval).where(WishApproval.wish_id == wish_id)
    )).scalars().all()
    assert approvals == []


@pytest.mark.asyncio
async def test_submit_advance_companion_after_manual_cascade_succeeds(
    client, auth_headers, db_session, test_org, make_user,
):
    """После явного нажатия «Построить цепочку» (POST /approvers/cascade) —
    submit проходит нормально, как и у обычной заявки.

    Верхний согласующий обязан иметь право subsidy.edit (владелец, 2026-09-29:
    «верхним согласующим можно ставить только того, кто имеет право
    корректировать субсидию») — role="org_admin" даёт его по умолчанию
    (см. perm_seed_hotfix.sql), как и в test_wish_top_approver_subsidy_edit_gate.py."""
    manager = await make_user(
        role="org_admin", last_name="Козеев", first_name="Евгений", middle_name="Викторович",
    )
    test_org.director_last_name = "Козеев"
    test_org.director_first_name = "Евгений"
    test_org.director_middle_name = "Викторович"
    db_session.add(test_org)
    await db_session.commit()

    data = await _create_advance_purchase(client, auth_headers)
    wish_id = data["wish_id"]

    cascade_resp = await client.post(
        f"/api/wishes/{wish_id}/approvers/cascade",
        json={"top_user_id": manager.id, "mode": "sequential"},
        headers=auth_headers,
    )
    assert cascade_resp.status_code == 200, cascade_resp.text

    resp = await client.post(f"/api/wishes/{wish_id}/submit", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "submitted"

    approvals = (await db_session.execute(
        select(WishApproval).where(WishApproval.wish_id == wish_id)
    )).scalars().all()
    assert len(approvals) >= 1
    assert manager.id in {a.user_id for a in approvals}


@pytest.mark.asyncio
async def test_resubmit_already_submitted_wish_fails_clearly(
    client, auth_headers, db_session, test_org, make_user,
):
    # org_admin — имеет subsidy.edit по умолчанию, обязателен для верхнего
    # согласующего (см. test_wish_top_approver_subsidy_edit_gate.py).
    manager = await make_user(
        role="org_admin", last_name="Козеев", first_name="Евгений", middle_name="Викторович",
    )
    test_org.director_last_name = "Козеев"
    test_org.director_first_name = "Евгений"
    test_org.director_middle_name = "Викторович"
    db_session.add(test_org)
    await db_session.commit()

    data = await _create_advance_purchase(client, auth_headers)
    wish_id = data["wish_id"]

    cascade_resp = await client.post(
        f"/api/wishes/{wish_id}/approvers/cascade",
        json={"top_user_id": manager.id, "mode": "sequential"},
        headers=auth_headers,
    )
    assert cascade_resp.status_code == 200, cascade_resp.text

    first = await client.post(f"/api/wishes/{wish_id}/submit", headers=auth_headers)
    assert first.status_code == 200, first.text

    second = await client.post(f"/api/wishes/{wish_id}/submit", headers=auth_headers)
    assert second.status_code in (400, 409), second.text
    # Глобальный обработчик ошибок оборачивает HTTPException.detail в поле
    # "message" (см. e.payload.message во фронте, frontend/src/api.ts) — не "detail".
    assert second.json().get("message")


@pytest.mark.asyncio
async def test_submit_without_org_head_gives_clear_error(client, auth_headers):
    """Без единого согласующего (цепочка больше НЕ строится сама, см. тест выше) —
    409 с понятным текстом, указывающим на «Построить цепочку», не generic-«ошибка»."""
    data = await _create_advance_purchase(client, auth_headers)
    wish_id = data["wish_id"]

    resp = await client.post(f"/api/wishes/{wish_id}/submit", headers=auth_headers)
    assert resp.status_code == 409, resp.text
    message = resp.json().get("message", "")
    assert "не выбран согласующий" in message.lower()  # 30.09: руководитель не подбирается сам — нужен выбранный согласующий


@pytest.mark.asyncio
async def test_put_advance_purchase_draft_still_syncs_companion_items(
    client, auth_headers, db_session,
):
    data = await _create_advance_purchase(client, auth_headers, item_name="Такси", price=500)
    purchase_id = data["id"]
    wish_id = data["wish_id"]

    put_payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест",
        "items": [
            {
                "item_name": "Обед в кафе",
                "item_type": "услуга",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 750,
                "total_price": 750,
            }
        ],
    }
    resp = await client.put(f"/api/purchases/{purchase_id}", json=put_payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    wish = await db_session.get(Wish, wish_id)
    assert wish.status == "draft"  # PUT не должен трогать статус

    wish_items = (await db_session.execute(
        select(WishItem).where(WishItem.wish_id == wish_id)
    )).scalars().all()
    names = {wi.item_name for wi in wish_items}
    assert names == {"Обед в кафе"}
