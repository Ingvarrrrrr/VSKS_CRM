"""Тесты задач A/B/C/D сессии 2026-09-20 (владелец, лист 2 №2/№3):

  A. app/services/wish_multi_sync.py — синхронизация заявки, распределённой
     на НЕСКОЛЬКО закупок, при повторном согласовании.
  B. DELETE /api/wishes/{wish_id}/distribution — app/routers/wish_distribution_reset.py.
  C. POST /api/purchases/{pid}/items/{item_id}/move — app/routers/purchase_items_move.py.
  D. GET /api/wishes/{wish_id}/purchases-board — app/routers/wish_purchases_board.py.

По образцу tests/test_wish_approve_distribution.py — тело фикстуры _seed_wish_two_groups
переиспользует те же приёмы (Subsidy с require_planned_dates=False, FeoCategory
уровня 1 как фолбэк заявки, Product.category как ключ группы).
"""
import pytest
from sqlalchemy import select
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.product import Product
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory


async def _seed_wish_two_groups(db_session, test_org, test_user):
    """Заявка с 2 позициями, резолвящимися в 2 РАЗНЫЕ группы по product.category
    (Электроника / Мебель) — approve-distribution (split=True по умолчанию)
    создаёт из неё ровно 2 закупки."""
    subsidy = Subsidy(name=f"TestSubsidy-{id(db_session)}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    feo_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Прочее")
    db_session.add(feo_cat)
    await db_session.flush()

    p_elec = Product(name=f"Laptop-{id(db_session)}", category="Электроника", org_id=test_org.id)
    p_furn = Product(name=f"Chair-{id(db_session)}", category="Мебель", org_id=test_org.id)
    db_session.add_all([p_elec, p_furn])
    await db_session.flush()

    w = Wish(
        org_id=test_org.id,
        title="Комплект для офиса",
        status="submitted",
        created_by=test_user.id,
        subsidy_id=subsidy.id,
        feo_category_id=feo_cat.id,
    )
    db_session.add(w)
    await db_session.flush()

    item_laptop = WishItem(
        wish_id=w.id, product_id=p_elec.id, item_name="Laptop",
        quantity=1, unit_price=50000, total_price=50000,
    )
    item_chair = WishItem(
        wish_id=w.id, product_id=p_furn.id, item_name="Chair",
        quantity=3, unit_price=5000, total_price=15000,
    )
    db_session.add_all([item_laptop, item_chair])
    await db_session.commit()
    await db_session.refresh(item_laptop)
    await db_session.refresh(item_chair)
    return w, item_laptop, item_chair


async def _purchases_of(db_session, wish_id):
    res = await db_session.execute(
        select(Purchase).where(Purchase.wish_id == wish_id).order_by(Purchase.id)
    )
    return res.scalars().all()


async def _purchase_by_subject_substr(db_session, wish_id, substr):
    purchases = await _purchases_of(db_session, wish_id)
    for p in purchases:
        if substr in (p.subject or ""):
            return p
    raise AssertionError(f"No purchase with {substr!r} in subject among {[p.subject for p in purchases]}")


@pytest.mark.asyncio
async def test_multi_sync_edit_routes_change_to_correct_purchase(
    client, db_session, admin_headers, superadmin_headers, test_org, test_user,
):
    """(1) заявка на 2 закупки -> откат -> правка позиции в черновике ->
    повторное согласование -> изменение попало в НУЖНУЮ закупку, разбивка
    (2 закупки) сохранена."""
    w, item_laptop, item_chair = await _seed_wish_two_groups(db_session, test_org, test_user)

    approve = await client.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)
    assert approve.status_code == 200, approve.text
    assert approve.json()["count"] == 2

    purchases_before = await _purchases_of(db_session, w.id)
    assert len(purchases_before) == 2
    assert all(p.status == "plan_schedule" for p in purchases_before)

    # Откат: force draft прячет закупки в статус 'wishes'.
    back = await client.post(
        f"/api/wishes/{w.id}/status", json={"status": "draft"}, headers=superadmin_headers,
    )
    assert back.status_code == 200, back.text
    purchases_hidden = await _purchases_of(db_session, w.id)
    assert all(p.status == "wishes" for p in purchases_hidden)

    # Правка позиции ПРЯМО в черновике (как это делает форма заявки). Меняем
    # ТОЛЬКО имя (не цену/сумму) — рост цены сверх авто-заведённой плановой
    # позиции (auto_assign_planned_items при первом распределении завёл план
    # РОВНО под исходную сумму) регистрировался бы запросом на согласование
    # превышения (см. app.services.tz_excess_approval) — отдельный механизм,
    # не то, что здесь проверяется.
    item_laptop.item_name = "Laptop Pro"
    db_session.add(item_laptop)
    await db_session.commit()

    # Повторное согласование (force 'converted' — тот же путь, что и обычное
    # повторное, но surfaced purchase_sync в ответе, см. wish_transitions.py).
    reapprove = await client.post(
        f"/api/wishes/{w.id}/status", json={"status": "converted"}, headers=superadmin_headers,
    )
    assert reapprove.status_code == 200, reapprove.text
    body = reapprove.json()
    sync = body.get("purchase_sync")
    assert sync is not None, f"Expected purchase_sync in response, got: {body}"
    assert len(sync.get("purchases") or []) == 2, f"Expected 2 per-purchase reports: {sync}"

    # Разбивка сохранена — по-прежнему 2 закупки заявки, не пересозданы (id совпадают).
    purchases_after = await _purchases_of(db_session, w.id)
    assert {p.id for p in purchases_after} == {p.id for p in purchases_before}
    assert all(p.status == "plan_schedule" for p in purchases_after)

    # Изменение попало ИМЕННО в закупку группы "Электроника" (там лежит Laptop).
    elec_purchase = await _purchase_by_subject_substr(db_session, w.id, "Электроника")
    furn_purchase = await _purchase_by_subject_substr(db_session, w.id, "Мебель")

    elec_items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == elec_purchase.id)
    )).scalars().all()
    assert len(elec_items) == 1
    assert elec_items[0].item_name == "Laptop Pro"

    # Закупка "Мебель" не затронута.
    furn_items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == furn_purchase.id)
    )).scalars().all()
    assert len(furn_items) == 1
    assert furn_items[0].item_name == "Chair"

    await db_session.refresh(elec_purchase)
    await db_session.refresh(furn_purchase)
    assert float(elec_purchase.planned_total_price) == 50000.0
    assert float(furn_purchase.planned_total_price) == 15000.0


@pytest.mark.asyncio
async def test_multi_sync_new_item_routed_by_group_key(
    client, db_session, admin_headers, superadmin_headers, test_org, test_user,
):
    """(2) новая позиция заявки (добавленная в черновике) попадает в закупку
    ПО КЛЮЧУ группы (product.category), а не в первую попавшуюся."""
    w, item_laptop, item_chair = await _seed_wish_two_groups(db_session, test_org, test_user)

    approve = await client.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)
    assert approve.status_code == 200, approve.text

    await client.post(f"/api/wishes/{w.id}/status", json={"status": "draft"}, headers=superadmin_headers)

    # Новая позиция заявки — того же товара/категории, что Laptop (Электроника).
    elec_product_id = item_laptop.product_id
    new_item = WishItem(
        wish_id=w.id, product_id=elec_product_id, item_name="Mouse",
        quantity=2, unit_price=1000, total_price=2000,
    )
    db_session.add(new_item)
    await db_session.commit()

    reapprove = await client.post(
        f"/api/wishes/{w.id}/status", json={"status": "converted"}, headers=superadmin_headers,
    )
    assert reapprove.status_code == 200, reapprove.text
    sync = reapprove.json().get("purchase_sync") or {}
    added_names = {i["name"] for i in (sync.get("items_added") or [])}
    assert "Mouse" in added_names, f"Expected Mouse in items_added, got: {sync}"

    elec_purchase = await _purchase_by_subject_substr(db_session, w.id, "Электроника")
    furn_purchase = await _purchase_by_subject_substr(db_session, w.id, "Мебель")

    elec_names = {
        it.item_name for it in (await db_session.execute(
            select(PurchaseItem).where(PurchaseItem.purchase_id == elec_purchase.id)
        )).scalars().all()
    }
    furn_names = {
        it.item_name for it in (await db_session.execute(
            select(PurchaseItem).where(PurchaseItem.purchase_id == furn_purchase.id)
        )).scalars().all()
    }
    assert elec_names == {"Laptop", "Mouse"}, elec_names
    assert furn_names == {"Chair"}, furn_names


@pytest.mark.asyncio
async def test_move_item_between_sibling_purchases_recalculates_both(
    client, db_session, admin_headers, test_org, test_user,
):
    """(3) move между сестринскими закупками одной заявки пересчитывает суммы обеих."""
    w, item_laptop, item_chair = await _seed_wish_two_groups(db_session, test_org, test_user)
    approve = await client.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)
    assert approve.status_code == 200, approve.text

    elec_purchase = await _purchase_by_subject_substr(db_session, w.id, "Электроника")
    furn_purchase = await _purchase_by_subject_substr(db_session, w.id, "Мебель")
    chair_item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == furn_purchase.id)
    )).scalars().one()

    resp = await client.post(
        f"/api/purchases/{furn_purchase.id}/items/{chair_item.id}/move",
        json={"target_purchase_id": elec_purchase.id},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["item_id"] == chair_item.id
    assert body["source"]["id"] == furn_purchase.id
    assert body["target"]["id"] == elec_purchase.id
    assert body["source"]["items_count"] == 0
    assert body["target"]["items_count"] == 2
    # recalc_purchase_money НЕ обнуляет план закупки, у которой не осталось ни
    # одной PurchaseItem (см. _load_items_total в purchase_money_writer.py —
    # «закупка без единой позиции ... не должна обнуляться» — тот же принцип,
    # что бережёт авансовые отчёты без ТЗ-строк; это НЕ второй писатель, тот
    # же recalc_purchase_money, вызванный на обе закупки). planned_total_price
    # source остаётся зафиксированным на последнем известном значении.
    assert float(body["source"]["planned_total_price"]) == 15000.0
    assert float(body["target"]["planned_total_price"]) == 65000.0  # 50000 + 15000

    await db_session.refresh(chair_item)
    assert chair_item.purchase_id == elec_purchase.id

    await db_session.refresh(elec_purchase)
    await db_session.refresh(furn_purchase)
    assert float(elec_purchase.planned_total_price) == 65000.0


@pytest.mark.asyncio
async def test_move_item_into_frozen_purchase_returns_409(
    client, db_session, admin_headers, test_org, test_user,
):
    """(4) move в замороженную (TZ_FROZEN_STATUSES) закупку -> 409."""
    w, item_laptop, item_chair = await _seed_wish_two_groups(db_session, test_org, test_user)
    approve = await client.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)
    assert approve.status_code == 200, approve.text

    elec_purchase = await _purchase_by_subject_substr(db_session, w.id, "Электроника")
    furn_purchase = await _purchase_by_subject_substr(db_session, w.id, "Мебель")
    furn_purchase.status = "contracted"
    db_session.add(furn_purchase)
    await db_session.commit()

    laptop_item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == elec_purchase.id)
    )).scalars().one()

    resp = await client.post(
        f"/api/purchases/{elec_purchase.id}/items/{laptop_item.id}/move",
        json={"target_purchase_id": furn_purchase.id},
        headers=admin_headers,
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_reset_distribution_deletes_hidden_and_blocks_plan_schedule(
    client, db_session, admin_headers, superadmin_headers, test_org, test_user,
):
    """(5) reset при скрытых (status='wishes') закупках удаляет их; при закупке
    в plan_schedule -> 409."""
    w, item_laptop, item_chair = await _seed_wish_two_groups(db_session, test_org, test_user)
    approve = await client.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)
    assert approve.status_code == 200, approve.text

    # Пока закупки в plan_schedule -> сброс запрещён.
    blocked = await client.delete(f"/api/wishes/{w.id}/distribution", headers=admin_headers)
    assert blocked.status_code == 409, blocked.text

    # Откат -> закупки скрыты (status='wishes').
    back = await client.post(f"/api/wishes/{w.id}/status", json={"status": "draft"}, headers=superadmin_headers)
    assert back.status_code == 200, back.text

    reset = await client.delete(f"/api/wishes/{w.id}/distribution", headers=admin_headers)
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["wish_id"] == w.id
    assert len(body["deleted_purchase_ids"]) == 2

    remaining = await _purchases_of(db_session, w.id)
    assert remaining == []

    await db_session.refresh(w)
    assert w.purchase_id is None


@pytest.mark.asyncio
async def test_purchases_board_returns_both_purchases_with_items(
    client, db_session, admin_headers, test_org, test_user,
):
    """(6) purchases-board отдаёт обе закупки заявки с их позициями и
    _product_category, согласованной с PurchaseSplitKanban.vue."""
    w, item_laptop, item_chair = await _seed_wish_two_groups(db_session, test_org, test_user)
    approve = await client.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)
    assert approve.status_code == 200, approve.text

    resp = await client.get(f"/api/wishes/{w.id}/purchases-board", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["wish_id"] == w.id
    purchases = body["purchases"]
    assert len(purchases) == 2

    by_category: dict = {}
    for p in purchases:
        assert p["frozen"] is False
        for it in p["items"]:
            by_category[it["item_name"]] = it["_product_category"]

    assert by_category.get("Laptop") == "Электроника"
    assert by_category.get("Chair") == "Мебель"
