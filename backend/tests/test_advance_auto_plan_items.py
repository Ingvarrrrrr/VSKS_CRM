# -*- coding: utf-8 -*-
"""Авто-план для авансовых отчётов (владелец, 30.09.2026, решение повторное и
жёсткое): «Из авансового все позиции АВТОМАТИЧЕСКИ привязываются к плану. Не
надо там искать сопоставление. Это отдельная покупка, которую человек принёс в
чеке — её не было в плане. Не сопоставляем».

Покрывает app/services/advance_auto_plan.py::sync_advance_auto_plan_items и его
вызовы из create_purchase/update_purchase (purchases.py) и patch_purchase_item
(purchase_items_edit.py):

  1. Две одноимённые позиции («Доставка») из РАЗНЫХ чеков в ОДНОЙ категории —
     каждая получает СВОЮ FeoPlannedItem (НЕ схлопываются в одну, в отличие от
     общего plan_autoassign.auto_assign_planned_items), суммы совпадают со
     строками, превышения плана нет.
  2. Удаление позиции (PUT без неё) деактивирует её собственную авто-плановую,
     если на неё больше никто не ссылается.
  3. Правка цены/количества позиции (PATCH одной позиции) обновляет ЕЁ ЖЕ
     авто-плановую на месте — не заводит вторую и не создаёт ложное
     превышение плана.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.purchase_item import PurchaseItem
from app.models.feo_planned_item import FeoPlannedItem


async def _make_subsidy(db_session, budget=5_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        require_planned_dates=False,
        status="approved",  # assert_subsidy_approved_for_binding гейтит create/update_purchase
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, **kwargs):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        budget=kwargs.pop("budget", Decimal("1000000")),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


def _delivery_item(price: int, cat_id: int) -> dict:
    return {
        "item_name": "Доставка",
        "item_type": "услуга",
        "quantity": 1,
        "unit": "шт",
        "unit_price": price,
        "total_price": price,
        "feo_category_id": cat_id,
    }


@pytest.mark.asyncio
async def test_two_same_named_advance_items_get_separate_auto_plans(
    client, auth_headers, db_session,
):
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)

    create_payload = {
        "purchase_method": "advance",
        "subject": "Авансовый — тест авто-плана",
        "subsidy_id": subsidy.id,
        "items": [_delivery_item(300, cat.id), _delivery_item(450, cat.id)],
    }
    resp = await client.post("/api/purchases/", json=create_payload, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    purchase_id = body["id"]
    # Мягкий контроль превышения (assert_no_unapproved_excess) не должен
    # сработать — обе позиции ровно в рамках СВОИХ новых авто-плановых.
    assert not body.get("excess_warnings"), body.get("excess_warnings")

    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id).order_by(PurchaseItem.unit_price)
    )).scalars().all()
    assert len(items) == 2
    cheap, expensive = items[0], items[1]

    assert cheap.feo_planned_item_id is not None
    assert expensive.feo_planned_item_id is not None
    assert cheap.feo_planned_item_id != expensive.feo_planned_item_id, (
        "Владелец, 30.09.2026: одноимённые позиции авансового из разных чеков "
        "не должны схлопываться в одну плановую позицию"
    )
    assert cheap.over_plan is False
    assert expensive.over_plan is False

    fpi_cheap = await db_session.get(FeoPlannedItem, cheap.feo_planned_item_id)
    fpi_expensive = await db_session.get(FeoPlannedItem, expensive.feo_planned_item_id)
    for fpi, item in ((fpi_cheap, cheap), (fpi_expensive, expensive)):
        assert fpi.auto_created is True
        assert fpi.is_active is True
        assert fpi.feo_category_id == cat.id
        assert fpi.name == "Доставка"
        assert Decimal(fpi.amount) == Decimal(item.total_price)
        assert Decimal(fpi.unit_price) == Decimal(item.unit_price)
        # Владелец (2026-09-01): позиция родилась из реального расхода, не из
        # файла ФЭО — см. resolve_origin_flags(feo_money=None, ...).
        assert fpi.is_feo_breakdown is False
        assert fpi.is_internal_plan is True

    # Активных плановых позиций «Доставка» в категории — ровно 2, не 1.
    active_named = (await db_session.execute(
        select(FeoPlannedItem).where(
            FeoPlannedItem.feo_category_id == cat.id,
            FeoPlannedItem.name == "Доставка",
            FeoPlannedItem.is_active == True,  # noqa: E712
        )
    )).scalars().all()
    assert len(active_named) == 2

    return purchase_id, cat, subsidy, cheap.id, expensive.id, fpi_cheap.id, fpi_expensive.id


@pytest.mark.asyncio
async def test_removing_advance_item_deactivates_its_own_auto_plan(
    client, auth_headers, db_session,
):
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)

    create_payload = {
        "purchase_method": "advance",
        "subject": "Авансовый — тест удаления позиции",
        "subsidy_id": subsidy.id,
        "items": [_delivery_item(300, cat.id), _delivery_item(450, cat.id)],
    }
    resp = await client.post("/api/purchases/", json=create_payload, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    purchase_id = resp.json()["id"]

    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id).order_by(PurchaseItem.unit_price)
    )).scalars().all()
    cheap, expensive = items[0], items[1]
    removed_fpi_id = expensive.feo_planned_item_id
    kept_fpi_id = cheap.feo_planned_item_id
    assert removed_fpi_id is not None and kept_fpi_id is not None

    # PUT без второй позиции (владелец удалил строку из авансового отчёта).
    put_payload = dict(create_payload)
    put_payload["items"] = [{
        "item_name": cheap.item_name,
        "item_type": cheap.item_type,
        "quantity": float(cheap.quantity),
        "unit": cheap.unit,
        "unit_price": float(cheap.unit_price),
        "total_price": float(cheap.total_price),
        "feo_category_id": cheap.feo_category_id,
        "feo_planned_item_id": cheap.feo_planned_item_id,
        "over_plan": cheap.over_plan,
    }]
    put_resp = await client.put(f"/api/purchases/{purchase_id}", json=put_payload, headers=auth_headers)
    assert put_resp.status_code == 200, put_resp.text

    remaining_items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalars().all()
    assert len(remaining_items) == 1
    assert remaining_items[0].feo_planned_item_id == kept_fpi_id, (
        "Оставшаяся позиция обязана сохранить привязку к СВОЕЙ авто-плановой"
    )

    removed_fpi = await db_session.get(FeoPlannedItem, removed_fpi_id)
    await db_session.refresh(removed_fpi)
    assert removed_fpi.is_active is False, (
        "Авто-плановая позиция удалённой строки авансового обязана "
        "деактивироваться (plan_autoassign.deactivate_if_orphaned), иначе "
        "остаётся призраком в плане"
    )

    kept_fpi = await db_session.get(FeoPlannedItem, kept_fpi_id)
    assert kept_fpi.is_active is True


@pytest.mark.asyncio
async def test_editing_advance_item_price_updates_its_auto_plan_in_place(
    client, auth_headers, db_session,
):
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)

    create_payload = {
        "purchase_method": "advance",
        "subject": "Авансовый — тест правки цены",
        "subsidy_id": subsidy.id,
        "items": [_delivery_item(300, cat.id)],
    }
    resp = await client.post("/api/purchases/", json=create_payload, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    purchase_id = resp.json()["id"]

    item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalar_one()
    original_fpi_id = item.feo_planned_item_id
    assert original_fpi_id is not None

    # W3 (patch_purchase_item): пока закупка в статусе 'wishes', позиция,
    # привязанная к заявке-компаньону, правится только через заявку — реальная
    # правка цены/кол-ва в закупке происходит с момента «Плана закупок»,
    # переводим статус напрямую (тот же приём, что и в
    # test_advance_wish_execution_feo_link_sync.py — прямая мутация статуса,
    # workflow перехода здесь не при чём).
    from app.models.purchase import Purchase
    purchase = await db_session.get(Purchase, purchase_id)
    purchase.status = "plan_schedule"
    await db_session.commit()

    # Владелец, задача п.1: «если у позиции меняются количество/цена — её
    # авто-плановая обновляется так же (иначе будет ложное превышение)».
    patch_resp = await client.patch(
        f"/api/purchases/{purchase_id}/items/{item.id}",
        json={"quantity": 2, "unit_price": 300},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert not patch_resp.json().get("excess_warnings"), patch_resp.json().get("excess_warnings")

    await db_session.refresh(item)
    assert item.feo_planned_item_id == original_fpi_id, (
        "Правка кол-ва/цены не должна заводить вторую авто-плановую позицию"
    )
    assert float(item.quantity) == 2
    assert float(item.total_price) == 600

    fpi = await db_session.get(FeoPlannedItem, original_fpi_id)
    await db_session.refresh(fpi)
    assert Decimal(fpi.quantity) == Decimal("2")
    assert Decimal(fpi.amount) == Decimal("600")
    assert Decimal(fpi.unit_price) == Decimal("300")
