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


@pytest.mark.asyncio
async def test_final_decide_moves_advance_purchase_to_delivered_automatically(
    client, auth_headers, admin_headers, db_session, test_org, make_user,
):
    """Владелец (02.10.2026, quick-план «Деньги субсидии», шаг 6, вариант Б):
    «после ПОСЛЕДНЕГО согласования закупка авансового сразу попадает в статус
    "Поставлено, не оплачено", минуя plan_schedule/work_in_progress/
    contracted/ordered» — финальное согласование компаньона (последний/
    единственный согласующий в цепочке) само переводит закупку
    'wishes' -> 'delivered' ОДНИМ прыжком через то же ядро перехода
    (app/services/purchase_transition_core.py), без ручного клика и без
    промежуточных стадий. Чек загружен заранее — иначе гейт обязательных
    полей 'delivered' (acceptance_doc_*) отказал бы (см. следующий тест)."""
    from app.models.purchase_receipt import PurchaseReceipt

    # org_admin — имеет subsidy.edit по умолчанию, обязателен для верхнего
    # согласующего (владелец, 2026-09-29; см. test_wish_top_approver_subsidy_edit_gate.py).
    manager = await make_user(role="org_admin", last_name="Иванов")

    data = await _create_advance_purchase(client, auth_headers)
    purchase_id = data["id"]
    wish_id = data["wish_id"]

    db_session.add(PurchaseReceipt(purchase_id=purchase_id, fiscal_document_number=901, source="manual"))
    await db_session.commit()

    cascade_resp = await client.post(
        f"/api/wishes/{wish_id}/approvers/cascade",
        json={"top_user_id": manager.id, "mode": "sequential"},
        headers=auth_headers,
    )
    assert cascade_resp.status_code == 200, cascade_resp.text
    approval_id = cascade_resp.json()["approvers"][0]["id"]

    submit_resp = await client.post(f"/api/wishes/{wish_id}/submit", headers=auth_headers)
    assert submit_resp.status_code == 200, submit_resp.text

    decide_resp = await client.post(
        f"/api/wishes/{wish_id}/approvers/{approval_id}/decide",
        json={"decision": "approved", "comment": "решаю за менеджера в тесте"},
        headers=admin_headers,
    )
    assert decide_resp.status_code == 200, decide_resp.text
    body = decide_resp.json()
    assert body["status"] == "converted"
    assert body.get("advance_purchase_transition_warning") is None, body

    purchase_get = await client.get(f"/api/purchases/{purchase_id}", headers=auth_headers)
    assert purchase_get.status_code == 200, purchase_get.text
    assert purchase_get.json()["status"] == "delivered"


@pytest.mark.asyncio
async def test_final_decide_without_receipt_leaves_advance_in_wishes_with_warning(
    client, auth_headers, admin_headers, db_session, test_org, make_user,
):
    """Без чека/акта приёмки гейт обязательных полей 'delivered' отказывает —
    согласование компаньона НЕ должно падать (владелец: «не роняем согласование,
    закупка остаётся в wishes, причина — в предупреждении»), кнопка
    «→ План закупок»/повторный ручной прыжок остаётся доступна в карточке."""
    manager = await make_user(role="org_admin", last_name="Петров")

    data = await _create_advance_purchase(client, auth_headers)
    purchase_id = data["id"]
    wish_id = data["wish_id"]

    cascade_resp = await client.post(
        f"/api/wishes/{wish_id}/approvers/cascade",
        json={"top_user_id": manager.id, "mode": "sequential"},
        headers=auth_headers,
    )
    assert cascade_resp.status_code == 200, cascade_resp.text
    approval_id = cascade_resp.json()["approvers"][0]["id"]

    submit_resp = await client.post(f"/api/wishes/{wish_id}/submit", headers=auth_headers)
    assert submit_resp.status_code == 200, submit_resp.text

    decide_resp = await client.post(
        f"/api/wishes/{wish_id}/approvers/{approval_id}/decide",
        json={"decision": "approved", "comment": "решаю за менеджера в тесте"},
        headers=admin_headers,
    )
    assert decide_resp.status_code == 200, decide_resp.text
    body = decide_resp.json()
    assert body["status"] == "converted"
    assert body.get("advance_purchase_transition_warning"), body

    purchase_get = await client.get(f"/api/purchases/{purchase_id}", headers=auth_headers)
    assert purchase_get.status_code == 200, purchase_get.text
    assert purchase_get.json()["status"] == "wishes"
