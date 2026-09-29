# -*- coding: utf-8 -*-
"""PUT /api/wishes/{id} на согласованной ('converted') заявке с правкой items —
409, текст обязан называть РЕАЛЬНУЮ действующую закупку (владелец, 2026-09-29,
прод-баг: заявка №85/закупка №960 — текст показывал «закупку №636», хотя у
заявки одна закупка — 960).

Причина была в app/routers/wishes.py::update_wish (гейт items на converted):
  1) `p.purchase_number or p.id` — purchase_number почти всегда NULL (легаси
     поле), текст ВСЕГДА падал на голый p.id, а не реестровый номер;
  2) `_wish_linked_purchases` не фильтровала по статусу — отменённая закупка
     от более раннего переоформления (app/services/wish_advance_conversion.py)
     могла остаться привязанной к той же заявке и попасть в список первой.
"""
import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.purchase import Purchase


@pytest.mark.asyncio
async def test_converted_wish_edit_names_real_registry_number_not_raw_id(
    client, auth_headers, db_session, test_org,
):
    resp = await client.post(
        "/api/wishes/",
        json={
            "title": "Кабель для сервера",
            "items": [{
                "item_name": "Кабель", "item_type": "товар",
                "quantity": 1, "unit": "шт", "unit_price": 1000, "total_price": 1000,
            }],
        },
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    wish_id = resp.json()["id"]

    wish = await db_session.get(Wish, wish_id)
    wish.status = "converted"
    db_session.add(wish)
    purchase = Purchase(
        wish_id=wish_id, status="plan_schedule",
        subject="Кабель для сервера",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    assert purchase.registry_number, "registry_number обязан проставляться при INSERT (see _assign_purchase_registry_number)"

    items_res = await db_session.execute(select(WishItem).where(WishItem.wish_id == wish_id))
    item = items_res.scalars().first()

    put_resp = await client.put(
        f"/api/wishes/{wish_id}",
        json={"items": [{
            "id": item.id, "item_name": "Кабель другой", "item_type": "товар",
            "quantity": 1, "unit": "шт", "unit_price": 1000, "total_price": 1000,
        }]},
        headers=auth_headers,
    )
    assert put_resp.status_code == 409, put_resp.text
    message = put_resp.json().get("message") or put_resp.json().get("detail") or ""
    assert purchase.registry_number in message, message
    # Голый ID закупки (баг с прода) — не должен фигурировать как "номер".
    assert f"№{purchase.id})" not in message


@pytest.mark.asyncio
async def test_converted_wish_edit_ignores_cancelled_stale_purchase(
    client, auth_headers, db_session, test_org,
):
    """Отменённая закупка от старого переоформления не должна попадать в текст
    ошибки — действующая закупка заявки единственная (не cancelled)."""
    resp = await client.post(
        "/api/wishes/",
        json={
            "title": "Кабель для сервера",
            "items": [{
                "item_name": "Кабель", "item_type": "товар",
                "quantity": 1, "unit": "шт", "unit_price": 1000, "total_price": 1000,
            }],
        },
        headers=auth_headers,
    )
    wish_id = resp.json()["id"]
    wish = await db_session.get(Wish, wish_id)
    wish.status = "converted"
    db_session.add(wish)

    stale = Purchase(
        wish_id=wish_id, status="cancelled",
        subject="Ошибочно заведённая (старая)",
    )
    real = Purchase(
        wish_id=wish_id, status="plan_schedule",
        subject="Кабель для сервера",
    )
    db_session.add_all([stale, real])
    await db_session.commit()
    await db_session.refresh(stale)
    await db_session.refresh(real)

    items_res = await db_session.execute(select(WishItem).where(WishItem.wish_id == wish_id))
    item = items_res.scalars().first()

    put_resp = await client.put(
        f"/api/wishes/{wish_id}",
        json={"items": [{
            "id": item.id, "item_name": "Кабель другой", "item_type": "товар",
            "quantity": 1, "unit": "шт", "unit_price": 1000, "total_price": 1000,
        }]},
        headers=auth_headers,
    )
    assert put_resp.status_code == 409, put_resp.text
    message = put_resp.json().get("message") or put_resp.json().get("detail") or ""
    assert real.registry_number in message
    assert stale.registry_number not in message
