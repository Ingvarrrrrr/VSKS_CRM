# -*- coding: utf-8 -*-
"""Прод-инцидент 01.10.2026: закупка РЕЕ-2026-00975 (id=975), заявка-компаньон
авансового №98 (source='advance_report'). Автор (Любарец) создала авансовый
БЕЗ субсидии, затем поставила subsidy_id=7 в КАРТОЧКЕ ЗАЯВКИ (PUT /wishes/98),
отправила на согласование, согласовали. Итог на проде: wish.subsidy_id=7,
purchase.subsidy_id=NULL — закупка пропала из реестра закупок и из реестра
авансовых (оба фильтруют по субсидии).

Причина: apply_wish_header_to_purchase (app/services/advance_wish_sync.py:112)
зеркалит шапку заявки (subsidy_id/feo_category_id/event_id) в закупку-компаньон
только из wish_transitions.py::patch_wish_execution (PATCH /wishes/{id}/execution,
правка согласующего) — полное сохранение формы заявки (PUT /wishes/{id},
routers/wishes.py::update_wish) этот вызов не делало вовсе.

Покрытие:
  1. Авансовая закупка без субсидии + заявка-компаньон → PUT заявки с
     subsidy_id=X мирроит X в purchase.subsidy_id (тот же механизм, что уже
     был в PATCH-ветке, см. test_advance_companion_not_locked_by_purchase_stage.py
     и wish_transitions.py:417-428 — здесь не вторая копия формулы, а
     переиспользование apply_wish_header_to_purchase).
  2. Контроль: обычная (не-авансовая) заявка — PUT с subsidy_id не трогает
     чужую, несвязанную закупку.
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.purchase import Purchase


async def _make_subsidy(db_session, budget=8_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        require_planned_dates=False,
        status="approved",  # assert_subsidy_approved_for_binding гейтит PUT
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _create_advance_purchase(client, auth_headers, price=500):
    payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест синхронизации субсидии PUT",
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


@pytest.mark.asyncio
async def test_put_wish_subsidy_syncs_to_advance_companion_purchase(
    client, auth_headers, db_session,
):
    data = await _create_advance_purchase(client, auth_headers)
    wish_id = data["wish_id"]
    purchase_id = data["id"]

    purchase = await db_session.get(Purchase, purchase_id)
    assert purchase.purchase_method == "advance"
    assert purchase.subsidy_id is None

    wish = await db_session.get(Wish, wish_id)
    assert wish.source == "advance_report"
    assert wish.subsidy_id is None

    subsidy = await _make_subsidy(db_session)

    resp = await client.put(
        f"/api/wishes/{wish_id}",
        json={"subsidy_id": subsidy.id},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    await db_session.refresh(wish)
    assert wish.subsidy_id == subsidy.id

    purchase = await db_session.get(Purchase, purchase_id)
    await db_session.refresh(purchase)
    assert purchase.subsidy_id == subsidy.id, (
        "PUT /wishes/{id} обязан зеркалить subsidy_id заявки-компаньона "
        "авансового в связанную закупку (apply_wish_header_to_purchase) — "
        "иначе закупка пропадает из реестров, отфильтрованных по субсидии "
        "(прод-инцидент РЕЕ-2026-00975/заявка №98, 01.10.2026)."
    )


@pytest.mark.asyncio
async def test_put_regular_wish_subsidy_does_not_touch_unrelated_purchase(
    client, auth_headers, db_session, test_org,
):
    """Контроль: обычная (не-авансовая) заявка не связана с закупкой через
    этот механизм — мирроящий блок в update_wish гейтится source=='advance_report'
    и не должен задевать посторонние закупки."""
    subsidy = await _make_subsidy(db_session)
    other_subsidy = await _make_subsidy(db_session)

    # Несвязанная закупка (НЕ авансовая, НЕ привязана к заявке ниже) с уже
    # проставленной своей субсидией — сторож того, что мирроящий блок никого
    # лишнего не трогает.
    adv = await _create_advance_purchase(client, auth_headers)
    unrelated_purchase = await db_session.get(Purchase, adv["id"])
    unrelated_purchase.subsidy_id = other_subsidy.id
    db_session.add(unrelated_purchase)
    await db_session.commit()

    resp = await client.post(
        "/api/wishes/",
        json={"title": "Обычная заявка — тест контроля", "quantity": 1, "unit": "шт"},
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    wish_id = resp.json()["id"]

    wish = await db_session.get(Wish, wish_id)
    assert wish.source != "advance_report"

    resp = await client.put(
        f"/api/wishes/{wish_id}",
        json={"subsidy_id": subsidy.id},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    await db_session.refresh(wish)
    assert wish.subsidy_id == subsidy.id

    await db_session.refresh(unrelated_purchase)
    assert unrelated_purchase.subsidy_id == other_subsidy.id
