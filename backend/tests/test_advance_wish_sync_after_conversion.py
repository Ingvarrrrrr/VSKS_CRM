# -*- coding: utf-8 -*-
"""Прод-инцидент (30.09.2026, закупка РЕЕ-2026-00963 / заявка-компаньон №93,
status='converted'): владелец поправил в авансовой закупке цену позиции
«Бур по бетону» 700 → 95 ₽ и удалил позицию на 400 000 ₽. purchase_items
обновились, а wish_items заявки-компаньона остались старой копией (700 ₽ и
удалённая позиция на месте) — потому что синхронизация в
app/routers/purchases.py::update_purchase была ограничена статусами
('draft', 'submitted', 'rejected') и пропускала уже согласованный/
сконвертированный компаньон, хотя человек НИКОГДА не правит компаньон
напрямую после конверсии (правка wish.items на converted заблокирована в
update_wish) — источник истины всегда purchase_items закупки (ПРАВИЛО №6).

Покрытие:
  1. Компаньон в статусе 'converted' → PUT закупки с изменённой ценой/
     составом всё равно пересобирает wish_items (та же ветка, что и для
     draft, см. test_advance_reimbursement_wish_draft.py::
     test_put_advance_purchase_draft_still_syncs_companion_items).
  2. После такого PUT проверка превышения ТЗ над плановой позицией
     (collect_tz_over_plan_violations), которую видит дальнейшее движение
     закупки (assert_no_pending_tz_excess в purchase_transition_core.py),
     не находит нарушений ни по purchase_items, ни по свежим wish_items —
     до фикса wish_items хранили старую (превышающую план) цену и дали бы
     ложное нарушение при чтении заявки.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.tz_excess_approval import collect_tz_over_plan_violations


async def _create_advance_purchase(client, auth_headers, item_name="Бур по бетону", price=700, **extra):
    payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест синхронизации после конверсии",
        "items": [
            {
                "item_name": item_name,
                "item_type": "товар",
                "quantity": 1,
                "unit": "шт",
                "unit_price": price,
                "total_price": price,
            }
        ],
        **extra,
    }
    resp = await client.post("/api/purchases/", json=payload, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def _make_subsidy(db_session, budget=8_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        require_planned_dates=False,
        status="approved",
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


async def _make_planned_item(db_session, feo_category_id, **kwargs):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=kwargs.pop("name", "Бур по бетону"),
        quantity=kwargs.pop("quantity", Decimal("1")),
        unit=kwargs.pop("unit", "шт"),
        amount=kwargs.pop("amount", Decimal("100")),
        **kwargs,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


@pytest.mark.asyncio
async def test_put_advance_purchase_converted_still_syncs_companion_items(
    client, auth_headers, db_session,
):
    data = await _create_advance_purchase(client, auth_headers, item_name="Бур по бетону", price=700)
    purchase_id = data["id"]
    wish_id = data["wish_id"]

    # Компаньон уже полностью согласован (как заявка №93 на проде) — прямой
    # force-статус, без прогона через цепочку согласования (не предмет теста).
    wish = await db_session.get(Wish, wish_id)
    wish.status = "converted"
    wish.approved_by = wish.created_by
    await db_session.commit()

    put_payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест синхронизации после конверсии",
        "items": [
            {
                "item_name": "Бур по бетону",
                "item_type": "товар",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 95,
                "total_price": 95,
            }
        ],
    }
    resp = await client.put(f"/api/purchases/{purchase_id}", json=put_payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    await db_session.refresh(wish)
    assert wish.status == "converted"  # PUT закупки не трогает статус заявки

    wish_items = (await db_session.execute(
        select(WishItem).where(WishItem.wish_id == wish_id)
    )).scalars().all()
    assert len(wish_items) == 1
    assert wish_items[0].item_name == "Бур по бетону"
    assert Decimal(str(wish_items[0].unit_price)) == Decimal("95")
    assert Decimal(str(wish_items[0].total_price)) == Decimal("95")


@pytest.mark.asyncio
async def test_put_advance_purchase_converted_removes_deleted_item_from_companion(
    client, auth_headers, db_session,
):
    """Владелец удалил позицию на 400 000 ₽ в закупке — компаньон обязан
    её тоже потерять, а не хранить призрак."""
    data = await _create_advance_purchase(client, auth_headers, item_name="Бур по бетону", price=700)
    purchase_id = data["id"]
    wish_id = data["wish_id"]

    # Добавляем вторую позицию прямо в закупке (симулируем состояние "было
    # две строки"), затем PUT с ОДНОЙ строкой — как реальная правка владельца.
    put_two_items = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест синхронизации после конверсии",
        "items": [
            {
                "item_name": "Бур по бетону",
                "item_type": "товар",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 700,
                "total_price": 700,
            },
            {
                "item_name": "Лишняя позиция",
                "item_type": "товар",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 400000,
                "total_price": 400000,
            },
        ],
    }
    resp = await client.put(f"/api/purchases/{purchase_id}", json=put_two_items, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    wish = await db_session.get(Wish, wish_id)
    wish.status = "converted"
    wish.approved_by = wish.created_by
    await db_session.commit()

    put_one_item = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест синхронизации после конверсии",
        "items": [
            {
                "item_name": "Бур по бетону",
                "item_type": "товар",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 95,
                "total_price": 95,
            },
        ],
    }
    resp = await client.put(f"/api/purchases/{purchase_id}", json=put_one_item, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    wish_items = (await db_session.execute(
        select(WishItem).where(WishItem.wish_id == wish_id)
    )).scalars().all()
    names = {wi.item_name for wi in wish_items}
    assert names == {"Бур по бетону"}


@pytest.mark.asyncio
async def test_tz_excess_check_after_price_fix_sees_no_violation_on_synced_wish_items(
    client, auth_headers, db_session, test_org,
):
    """Плановая позиция «Бур по бетону» — 100 ₽. Закупка сначала заведена с
    700 ₽ (превышение ТЗ над планом), затем владелец правит цену на 95 ₽
    (в рамках плана). Источник истины для дальнейшего движения закупки —
    purchase_items (assert_no_pending_tz_excess в
    app/services/purchase_transition_core.py уже читает p.items, не трогаем).
    Здесь проверяем СИММЕТРИЮ: раз компаньон теперь зеркалит закупку при
    любом статусе (см. тест выше), collect_tz_over_plan_violations по
    wish_items компаньона тоже больше не видит нарушения — до фикса они
    расходились (0 по closure/purchase_items, нарушение по wish_items)."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)
    fpi = await _make_planned_item(db_session, cat.id, amount=Decimal("100"))

    data = await _create_advance_purchase(
        client, auth_headers, item_name="Бур по бетону", price=700,
        subsidy_id=subsidy.id,
    )
    purchase_id = data["id"]
    wish_id = data["wish_id"]

    # Привязываем позицию закупки к плановой позиции напрямую в БД (минуя
    # авто-подбор — не предмет этого теста).
    pi = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalars().first()
    pi.feo_planned_item_id = fpi.id
    pi.feo_category_id = cat.id
    await db_session.commit()

    wish = await db_session.get(Wish, wish_id)
    wish.status = "converted"
    wish.approved_by = wish.created_by
    wish.subsidy_id = subsidy.id
    await db_session.commit()

    # Владелец правит цену — теперь в рамках плана (95 <= 100).
    put_payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест синхронизации после конверсии",
        "subsidy_id": subsidy.id,
        "items": [
            {
                "item_name": "Бур по бетону",
                "item_type": "товар",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 95,
                "total_price": 95,
                "feo_category_id": cat.id,
                "feo_planned_item_id": fpi.id,
            },
        ],
    }
    resp = await client.put(f"/api/purchases/{purchase_id}", json=put_payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    purchase_items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalars().all()
    violations_on_purchase = await collect_tz_over_plan_violations(
        db_session, purchase_items, fallback_category_id=cat.id,
    )
    assert violations_on_purchase == []

    wish_items = (await db_session.execute(
        select(WishItem).where(WishItem.wish_id == wish_id)
    )).scalars().all()
    assert Decimal(str(wish_items[0].unit_price)) == Decimal("95")
    violations_on_wish = await collect_tz_over_plan_violations(
        db_session, wish_items, fallback_category_id=cat.id,
    )
    assert violations_on_wish == []
