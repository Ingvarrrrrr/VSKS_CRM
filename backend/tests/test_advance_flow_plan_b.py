# -*- coding: utf-8 -*-
"""Квик-план 2026-10-02 («Деньги субсидии: законтрактовано, перераспределение,
экономия»), шаг 6 — авансовый отчёт, вариант Б:

  1. Заявка авансового уходит на согласование ЦЕПОЧКЕ любого числа согласующих
     (переиспользуем существующий механизм wish_approvals.py — ПРАВИЛО №6).
  2. После ПОСЛЕДНЕГО согласования закупка авансового прыгает ОДНИМ шагом
     'wishes' -> 'delivered' («Поставлено, не оплачено»), минуя plan_schedule/
     work_in_progress/contracted/ordered (app/services/wish_distribution.py).
  3. На стадии 'delivered' финальное решение директора — две операции:
     «Оплачено» (POST /purchases/{id}/transition?status=paid) и «Отказать в
     оплате» (POST /purchases/{id}/stop — существующий механизм остановки с
     причиной, порог расширен для purchase_method='advance' до 'paid', см.
     app/services/purchase_stop.py). Обе гейтятся НОВЫМ правом-галочкой
     'advance_payment_decision' (app/services/advance_payment_decision.py),
     а не общим 'purchase.status_change' — директор не автор и не согласующий
     цепочки.
  4. Решение фиксируется PurchaseEvent(event_type='advance_payment_decision')
     — кто (user_id), когда (created_at), что решил + основание (data).

Тестовые сценарии (по заданию):
  (a) цепочка из 2 согласующих — после первого статус не меняется, после
      второго -> delivered;
  (b) «Отказать в оплате» без причины -> 422; с причиной -> stopped_at
      заполнен, причина сохранена, запись решения есть;
  (c) «Оплачено» -> paid, запись решения есть;
  (d) пользователь без права -> 403 с понятной причиной;
  (e) неавансовая закупка — поведение переходов не изменилось.
"""
import datetime

import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseEvent
from app.models.purchase_receipt import PurchaseReceipt


ADVANCE_PAYMENT_DECISION = "advance_payment_decision"


async def _ensure_role_permission(db_session, role: str, key: str, granted: bool = True) -> None:
    """Идемпотентный грант — не через make_role_permission (голый INSERT,
    падает UniqueViolation, если backend_a уже перезапущен и свой idempotent
    сид app/startup/permission_seeds.py::_advance_payment_decision_action уже
    вставил ТУ ЖЕ строку в реальную dev-БД, на которой крутятся тесты —
    см. docstring db_session в conftest.py). Здесь — select-or-update/insert,
    работает одинаково до и после перезапуска backend_a."""
    from app.models.permission import RolePermission
    row = (await db_session.execute(
        select(RolePermission).where(RolePermission.role_name == role, RolePermission.key == key)
    )).scalar_one_or_none()
    if row is None:
        db_session.add(RolePermission(role_name=role, key=key, granted=granted))
    elif row.granted != granted:
        row.granted = granted
    await db_session.commit()


async def _create_advance_purchase(client, auth_headers, price=500):
    payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — quick-план 2026-10-02",
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


async def _add_receipt(db_session, purchase_id: int, fiscal_document_number: int = 777) -> None:
    """Чек, нужный для прохождения гейта обязательных полей 'delivered' у
    авансового (acceptance_doc_* заменяются на «есть чек», см.
    app/services/purchase_transition_core.py)."""
    db_session.add(PurchaseReceipt(
        purchase_id=purchase_id, fiscal_document_number=fiscal_document_number, source="manual",
    ))
    await db_session.commit()


# ---------------------------------------------------------------------------
# (a) Цепочка из 2 согласующих: после первого — не меняется, после второго
#     (последнего) — закупка прыгает в 'delivered'.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_two_approver_chain_jumps_to_delivered_only_after_last(
    client, auth_headers, db_session, make_user,
):
    from app.auth.jwt import create_access_token

    dept_head = await make_user(role="org_admin", last_name="Начальник")
    accountant = await make_user(role="org_admin", last_name="Бухгалтер")
    dept_head_headers = {"Authorization": f"Bearer {create_access_token({'sub': dept_head.username, 'org_id': dept_head.org_id})}"}
    accountant_headers = {"Authorization": f"Bearer {create_access_token({'sub': accountant.username, 'org_id': accountant.org_id})}"}

    data = await _create_advance_purchase(client, auth_headers)
    purchase_id = data["id"]
    wish_id = data["wish_id"]
    await _add_receipt(db_session, purchase_id)

    add1 = await client.post(
        f"/api/wishes/{wish_id}/approvers", json={"user_id": dept_head.id}, headers=auth_headers,
    )
    assert add1.status_code == 201, add1.text
    approval1_id = add1.json()["id"]
    add2 = await client.post(
        f"/api/wishes/{wish_id}/approvers", json={"user_id": accountant.id}, headers=auth_headers,
    )
    assert add2.status_code == 201, add2.text
    approval2_id = add2.json()["id"]

    submit_resp = await client.post(f"/api/wishes/{wish_id}/submit", headers=auth_headers)
    assert submit_resp.status_code == 200, submit_resp.text

    # После ПЕРВОГО (начальник отдела — «надо ли оплачивать») — заявка ещё
    # 'submitted', закупка ещё НЕ 'delivered'.
    resp1 = await client.post(
        f"/api/wishes/{wish_id}/approvers/{approval1_id}/decide",
        json={"decision": "approved"}, headers=dept_head_headers,
    )
    assert resp1.status_code == 200, resp1.text
    assert resp1.json()["status"] == "submitted"

    purchase_mid = await client.get(f"/api/purchases/{purchase_id}", headers=auth_headers)
    assert purchase_mid.json()["status"] == "wishes", purchase_mid.text

    # После ВТОРОГО (бухгалтер — «есть ли деньги», последний в цепочке) —
    # заявка 'converted', закупка ОДНИМ прыжком 'delivered'.
    resp2 = await client.post(
        f"/api/wishes/{wish_id}/approvers/{approval2_id}/decide",
        json={"decision": "approved"}, headers=accountant_headers,
    )
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert body2["status"] == "converted"
    assert body2.get("advance_purchase_transition_warning") is None, body2

    purchase_final = await client.get(f"/api/purchases/{purchase_id}", headers=auth_headers)
    assert purchase_final.json()["status"] == "delivered", purchase_final.text

    wish = await db_session.get(Wish, wish_id)
    assert wish.status == "converted"


# ---------------------------------------------------------------------------
# Фикстура-хелпер: авансовая закупка, уже в 'delivered' (через прямую правку
# статуса — транзиция уже покрыта тестом (a) выше, здесь интересует только
# финальное решение директора).
# ---------------------------------------------------------------------------

async def _make_delivered_advance_purchase(db_session, reimbursement_user_id: int) -> Purchase:
    p = Purchase(
        purchase_method="advance",
        status="delivered",
        subject="Авансовый — решение директора (тест)",
        reimbursement_user_id=reimbursement_user_id,
        contract_price=500,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


# ---------------------------------------------------------------------------
# (b) «Отказать в оплате»: без причины -> 422; с причиной -> stopped_at
#     заполнен, причина сохранена, запись решения есть.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refuse_payment_requires_reason_then_records_decision(
    client, auth_headers, admin_headers, test_admin_user, db_session, test_user,
):
    await _ensure_role_permission(db_session, "org_admin", ADVANCE_PAYMENT_DECISION, True)

    p = await _make_delivered_advance_purchase(db_session, reimbursement_user_id=test_user.id)

    # Без причины -> 422/400 с понятным текстом.
    resp_no_reason = await client.post(
        f"/api/purchases/{p.id}/stop", json={}, headers=admin_headers,
    )
    assert resp_no_reason.status_code in (400, 422), resp_no_reason.text
    msg = (resp_no_reason.json().get("detail") or resp_no_reason.json().get("message") or "")
    assert "причин" in msg.lower(), resp_no_reason.text

    # С причиной -> 200, stopped_at/stopped_reason заполнены, решение записано.
    resp = await client.post(
        f"/api/purchases/{p.id}/stop",
        json={"reason": "Директор отказал: не хватает подтверждающих документов"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stopped_at"] is not None
    assert body["stopped_reason"] == "Директор отказал: не хватает подтверждающих документов"

    events = (await db_session.execute(
        select(PurchaseEvent).where(
            PurchaseEvent.purchase_id == p.id,
            PurchaseEvent.event_type == "advance_payment_decision",
        )
    )).scalars().all()
    assert len(events) == 1, events
    assert events[0].data["decision"] == "refused"
    assert events[0].data["comment"] == "Директор отказал: не хватает подтверждающих документов"
    assert events[0].user_id == test_admin_user.id
    assert events[0].created_at is not None


# ---------------------------------------------------------------------------
# (c) «Оплачено» -> paid, запись решения есть.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_paid_records_decision(
    client, admin_headers, test_admin_user, db_session, test_user,
):
    await _ensure_role_permission(db_session, "org_admin", ADVANCE_PAYMENT_DECISION, True)

    p = await _make_delivered_advance_purchase(db_session, reimbursement_user_id=test_user.id)
    p.payment_doc_number = "ПП-1"
    p.payment_doc_date = datetime.date.today()
    p.payment_amount = 500
    db_session.add(p)
    await db_session.commit()

    resp = await client.post(
        f"/api/purchases/{p.id}/transition?status=paid", headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paid"

    events = (await db_session.execute(
        select(PurchaseEvent).where(
            PurchaseEvent.purchase_id == p.id,
            PurchaseEvent.event_type == "advance_payment_decision",
        )
    )).scalars().all()
    assert len(events) == 1, events
    assert events[0].data["decision"] == "paid"
    assert events[0].user_id == test_admin_user.id


# ---------------------------------------------------------------------------
# (d) Пользователь без права -> 403 с понятной причиной (оба действия).
#     test_user (employee, автор/владелец авансового) НЕ должен иметь права
#     решить за директора вопрос оплаты СВОЕГО ЖЕ отчёта — владелец-бай-пас
#     сознательно НЕ применяется (см. assert_can_decide_advance_payment).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_permission_gets_403_on_both_actions(client, auth_headers, test_user, db_session):
    p = await _make_delivered_advance_purchase(db_session, reimbursement_user_id=test_user.id)
    p.payment_doc_number = "ПП-2"
    p.payment_doc_date = datetime.date.today()
    p.payment_amount = 500
    db_session.add(p)
    await db_session.commit()

    resp_paid = await client.post(
        f"/api/purchases/{p.id}/transition?status=paid", headers=auth_headers,
    )
    assert resp_paid.status_code == 403, resp_paid.text
    msg_paid = (resp_paid.json().get("detail") or resp_paid.json().get("message") or "")
    assert "advance_payment_decision" in msg_paid or "решени" in msg_paid.lower()

    resp_refuse = await client.post(
        f"/api/purchases/{p.id}/stop", json={"reason": "причина есть"}, headers=auth_headers,
    )
    assert resp_refuse.status_code == 403, resp_refuse.text
    msg_refuse = (resp_refuse.json().get("detail") or resp_refuse.json().get("message") or "")
    assert "advance_payment_decision" in msg_refuse or "решени" in msg_refuse.lower()


# ---------------------------------------------------------------------------
# (e) Неавансовая закупка — поведение переходов НЕ изменилось: 'paid' всё ещё
#     гейтится общим 'purchase.status_change' (не новым правом), и остановка
#     всё ещё недоступна на стадии 'delivered' (порог — 'contracted', не 'paid').
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_advance_purchase_transitions_unchanged(
    client, auth_headers, admin_headers, db_session,
):
    p = Purchase(
        purchase_method="single",
        status="delivered",
        subject="Обычная закупка — контроль регрессии",
        acceptance_doc_name="Акт", acceptance_doc_date=datetime.date.today(),
        acceptance_doc_number="1", acceptance_doc_amount=500,
        payment_doc_number="ПП-3", payment_doc_date=datetime.date.today(), payment_amount=500,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    # employee без 'purchase.status_change' — как и раньше, 403 с ЕГО текстом
    # (не текстом нового 'advance_payment_decision').
    resp_employee = await client.post(
        f"/api/purchases/{p.id}/transition?status=paid", headers=auth_headers,
    )
    assert resp_employee.status_code == 403, resp_employee.text
    msg = (resp_employee.json().get("detail") or resp_employee.json().get("message") or "")
    assert "Изменение статуса закупки" in msg or "purchase.status_change" in msg
    assert "advance_payment_decision" not in msg

    # org_admin (purchase.status_change=True по умолчанию) — переход доступен,
    # и НИКАКОЙ advance_payment_decision-записи не создаётся (не авансовый).
    resp_admin = await client.post(
        f"/api/purchases/{p.id}/transition?status=paid", headers=admin_headers,
    )
    assert resp_admin.status_code == 200, resp_admin.text
    assert resp_admin.json()["status"] == "paid"

    events = (await db_session.execute(
        select(PurchaseEvent).where(
            PurchaseEvent.purchase_id == p.id,
            PurchaseEvent.event_type == "advance_payment_decision",
        )
    )).scalars().all()
    assert events == []

    # Остановка обычной закупки на стадии 'delivered' по-прежнему запрещена —
    # порог 'contracted' не сдвинулся (расширение до 'paid' — ТОЛЬКО для
    # purchase_method='advance', см. app/services/purchase_stop.py).
    p2 = Purchase(purchase_method="single", status="delivered", subject="Контроль порога остановки")
    db_session.add(p2)
    await db_session.commit()
    await db_session.refresh(p2)
    resp_stop = await client.post(f"/api/purchases/{p2.id}/stop", json={}, headers=admin_headers)
    assert resp_stop.status_code == 409, resp_stop.text
