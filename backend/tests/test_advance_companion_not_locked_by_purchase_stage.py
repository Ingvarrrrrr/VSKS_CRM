# -*- coding: utf-8 -*-
"""Компаньон авансового отчёта (Wish.source='advance_report') согласовывает
ВОЗМЕЩЕНИЕ сотруднику — оно нужно независимо от того, до какой стадии
(договор/оплата) дошла сама закупка расходов. Прод-инцидент (владелец,
30.09.2026): заявка №68 (source='advance_report', status='draft') — компаньон
авансового РЕЕ-2026-00941 (purchase.id=941, purchase_number=631,
status='contracted'), этот авансовый дошёл до договора ДО введения правила
«авансовый не идёт в план без согласования». Попытка отправить заявку на
согласование отказывала 409 «Заявка привязана к закупке — №631 ...» —
1) владелец не мог найти закупку «631» в реестре, т.к. это легаси-поле
   purchase_number, а не registry_number (см. app/services/purchase_label.py);
2) блокировка вообще не должна была сработать для source='advance_report' —
   см. app/routers/wishes.py::update_wish, гейт _wish_locked_descr теперь
   исключает advance_report-компаньонов, ПОКА правка не трогает состав/цены
   (body.items) — это единственное, что остаётся заблокированным.

Покрытие:
  1. Закупка авансового в статусе 'contracted' + purchase_number=631 (легаси,
     отличается от registry_number) — PUT /wishes/{id} НЕ по items (например,
     desired_date) проходит 200, несмотря на contracted-lock.
  2. POST /wishes/{id}/submit того же компаньона (после явного построения
     цепочки согласующих) — тоже проходит 200, несмотря на contracted-lock.
  3. PUT /wishes/{id} с правкой items (состав/цены) ВСЁ ЕЩЁ отклоняется 409 —
     блокировка остаётся для состава, просто не для остального.
  4. Текст 409 называет registry_number (РЕЕ-...), а НЕ purchase_number (631).
"""
import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.purchase import Purchase


async def _create_advance_purchase(client, auth_headers, price=500):
    payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест контрактного гейта",
        "items": [
            {
                "item_name": "Такси до вокзала",
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


async def _lock_purchase_as_contracted(db_session, purchase_id: int, legacy_purchase_number: int = 631):
    """Симулирует прод-случай: закупка дошла до договора (contracted) ДО
    введения правила «авансовый без согласования не идёт в план», и у неё
    (легаси) проставлен purchase_number, не совпадающий с registry_number —
    как у настоящей закупки 631/РЕЕ-2026-00941 с прода."""
    purchase = await db_session.get(Purchase, purchase_id)
    purchase.status = "contracted"
    purchase.purchase_number = legacy_purchase_number
    db_session.add(purchase)
    await db_session.commit()
    return purchase


@pytest.mark.asyncio
async def test_put_advance_companion_non_items_edit_not_blocked_by_contracted_purchase(
    client, auth_headers, db_session,
):
    data = await _create_advance_purchase(client, auth_headers)
    wish_id = data["wish_id"]
    purchase_id = data["id"]

    await _lock_purchase_as_contracted(db_session, purchase_id)

    resp = await client.put(
        f"/api/wishes/{wish_id}",
        json={"desired_date": "2026-10-15"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    wish = await db_session.get(Wish, wish_id)
    assert wish.source == "advance_report"


@pytest.mark.asyncio
async def test_put_advance_companion_items_edit_still_blocked_by_contracted_purchase(
    client, auth_headers, db_session,
):
    """Правка СОСТАВА/цен заявки остаётся запрещённой — только это, не всё
    остальное."""
    data = await _create_advance_purchase(client, auth_headers)
    wish_id = data["wish_id"]
    purchase_id = data["id"]

    await _lock_purchase_as_contracted(db_session, purchase_id, legacy_purchase_number=631)
    purchase = await db_session.get(Purchase, purchase_id)
    registry_number = purchase.registry_number
    assert registry_number and registry_number.startswith("РЕЕ-")

    resp = await client.put(
        f"/api/wishes/{wish_id}",
        json={"items": [{"item_name": "Другое такси", "item_type": "услуга",
                          "quantity": 1, "unit": "шт", "unit_price": 999, "total_price": 999}]},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    message = resp.json().get("message", "")
    assert "Заявка привязана к закупке" in message
    # ПРАВИЛО №6 / purchase_label: текст обязан называть registry_number
    # (номер, видимый в реестре закупок), НЕ легаси purchase_number (631) —
    # владелец не мог найти закупку «631» в реестре (прод, заявка №68).
    assert registry_number in message
    assert "631" not in message


@pytest.mark.asyncio
async def test_submit_advance_companion_not_blocked_by_contracted_purchase(
    client, auth_headers, db_session, test_org, make_user,
):
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
    purchase_id = data["id"]

    await _lock_purchase_as_contracted(db_session, purchase_id)

    cascade_resp = await client.post(
        f"/api/wishes/{wish_id}/approvers/cascade",
        json={"top_user_id": manager.id, "mode": "sequential"},
        headers=auth_headers,
    )
    assert cascade_resp.status_code == 200, cascade_resp.text

    resp = await client.post(f"/api/wishes/{wish_id}/submit", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "submitted"

    wish = await db_session.get(Wish, wish_id)
    assert wish.status == "submitted"


@pytest.mark.asyncio
async def test_regular_wish_items_lock_message_uses_registry_number_not_purchase_number(
    client, auth_headers, db_session, test_org, make_user,
):
    """_wish_locked_descr (app/services/wish_access.py) — единый источник
    текста блокировки, используется и для обычных (не-авансовых) заявок.
    Тот же покрытие для не-авансового пути: registry_number, не
    purchase_number, во ВСЕХ денежных/статусных текстах, не только у
    advance_report."""
    from app.services.wish_access import _wish_locked_descr

    data = await _create_advance_purchase(client, auth_headers)
    purchase_id = data["id"]
    purchase = await _lock_purchase_as_contracted(db_session, purchase_id, legacy_purchase_number=631)

    wish_id = data["wish_id"]
    descr = await _wish_locked_descr(wish_id, db_session)
    assert descr is not None
    assert purchase.registry_number in descr
    assert "631" not in descr
