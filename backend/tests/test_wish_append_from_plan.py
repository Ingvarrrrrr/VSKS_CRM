"""«Добавить забытое из субсидии» (wish_append_from_plan, 29.10.2026) —
присоединение плановых позиций к УЖЕ существующей, распределённой на закупки
заявке + создание/переиспользование колонки «… — Добавляем забытое».

Сервисный слой (app/services/wish_append_from_plan.py) тестируется прямым
вызовом, по образцу test_plan_to_wish.py (вся интересующая логика лежит там,
роутер — тонкая обёртка, Правило №5). Фикстуры-хелперы (_make_subsidy_with_leaf/
_make_planned_item) переиспользованы из test_plan_to_wish.py — второй копии не
заводим (Правило №6)."""
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.plan_to_wish import PlanToWishItemInput
from app.services.wish_append_from_plan import (
    APPEND_FORGOTTEN_SUFFIX,
    append_items_from_plan,
)

from tests.test_plan_to_wish import _make_subsidy_with_leaf, _make_planned_item


async def _make_distributed_wish(db_session, subsidy, cat, test_user, org_id, title="Заявка на тест"):
    """Имитирует заявку, УЖЕ распределённую канбаном на одну закупку (как её
    оставляет app.services.wish_distribution._distribute_wish_to_purchases) —
    достаточно для проверки append_items_from_plan, без реального прогона
    всей конвертации."""
    wish = Wish(
        org_id=org_id, title=title, status="converted", created_by=test_user.id,
        subsidy_id=subsidy.id, feo_category_id=cat.id,
    )
    db_session.add(wish)
    await db_session.flush()

    purchase = Purchase(
        wish_id=wish.id, subsidy_id=subsidy.id, feo_category_id=cat.id,
        item_name=title, subject=title, status="plan_schedule",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(wish)
    return wish, purchase


@pytest.mark.asyncio
async def test_append_creates_wish_items_and_append_purchase(db_session, test_user, test_org):
    subsidy, cat = await _make_subsidy_with_leaf(
        db_session, "Subsidy-append-basic", org_id=test_org.id, visible_to_user_id=test_user.id,
    )
    planned = await _make_planned_item(db_session, cat, "Степлер", quantity=Decimal("10"), unit_price=Decimal("300"), amount=Decimal("3000"))
    wish, _existing_purchase = await _make_distributed_wish(db_session, subsidy, cat, test_user, test_org.id)

    items = [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=Decimal("2"), item_name="Степлер", price_source="plan")]
    result = await append_items_from_plan(db_session, test_user, wish.id, items)

    assert result["wish_id"] == wish.id
    assert result["items_count"] == 1

    wish_items = (await db_session.execute(select(WishItem).where(WishItem.wish_id == wish.id))).scalars().all()
    assert len(wish_items) == 1
    wi = wish_items[0]
    assert wi.feo_planned_item_id == planned.id
    assert wi.from_plan is True

    purchase = (await db_session.execute(select(Purchase).where(Purchase.id == result["purchase_id"]))).scalar_one()
    assert purchase.wish_id == wish.id
    assert purchase.subsidy_id == subsidy.id
    assert (purchase.item_name or "").endswith(APPEND_FORGOTTEN_SUFFIX)

    pitems = (await db_session.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id))).scalars().all()
    assert len(pitems) == 1
    assert pitems[0].wish_item_id == wi.id
    assert pitems[0].feo_planned_item_id == planned.id
    assert pitems[0].quantity == Decimal("2")


@pytest.mark.asyncio
async def test_append_twice_reuses_same_column(db_session, test_user, test_org):
    """Повторное добавление идёт в ТУ ЖЕ колонку «Добавляем забытое», не
    плодит вторую (задача владельца, п.1)."""
    subsidy, cat = await _make_subsidy_with_leaf(
        db_session, "Subsidy-append-reuse", org_id=test_org.id, visible_to_user_id=test_user.id,
    )
    planned1 = await _make_planned_item(db_session, cat, "Бумага", quantity=Decimal("10"), unit_price=Decimal("300"), amount=Decimal("3000"), unit="упак")
    planned2 = await _make_planned_item(db_session, cat, "Скотч", quantity=Decimal("10"), unit_price=Decimal("100"), amount=Decimal("1000"))
    wish, _existing_purchase = await _make_distributed_wish(db_session, subsidy, cat, test_user, test_org.id)

    result1 = await append_items_from_plan(
        db_session, test_user, wish.id,
        [PlanToWishItemInput(feo_planned_item_id=planned1.id, quantity=Decimal("1"), item_name="Бумага", price_source="plan")],
    )
    result2 = await append_items_from_plan(
        db_session, test_user, wish.id,
        [PlanToWishItemInput(feo_planned_item_id=planned2.id, quantity=Decimal("1"), item_name="Скотч", price_source="plan")],
    )

    assert result1["purchase_id"] == result2["purchase_id"]

    append_purchases = (await db_session.execute(
        select(Purchase).where(Purchase.wish_id == wish.id, Purchase.item_name.like(f"%{APPEND_FORGOTTEN_SUFFIX}"))
    )).scalars().all()
    assert len(append_purchases) == 1, "должна быть ровно одна колонка «Добавляем забытое»"

    pitems = (await db_session.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == result1["purchase_id"]))).scalars().all()
    assert len(pitems) == 2


@pytest.mark.asyncio
async def test_append_over_residual_raises(db_session, test_user, test_org):
    """Превышение остатка плана — жёсткий отказ без обхода (409 — та же
    проверка, что у build_items_from_plan/create_wish_from_plan, Правило №6:
    второй расчёт остатка не заводим)."""
    subsidy, cat = await _make_subsidy_with_leaf(
        db_session, "Subsidy-append-over", org_id=test_org.id, visible_to_user_id=test_user.id,
    )
    planned = await _make_planned_item(db_session, cat, "Тонер", quantity=Decimal("2"), unit_price=Decimal("2000"), amount=Decimal("4000"))
    wish, _existing_purchase = await _make_distributed_wish(db_session, subsidy, cat, test_user, test_org.id)

    items = [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=Decimal("5"), item_name="Тонер", price_source="plan")]

    with pytest.raises(HTTPException) as exc_info:
        await append_items_from_plan(db_session, test_user, wish.id, items)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_append_foreign_subsidy_rejected(db_session, test_user, test_org):
    """Плановая позиция другой субсидии, чем у заявки — отказ (422, та же
    проверка build_items_from_plan, что у create_wish_from_plan)."""
    subsidy_a, cat_a = await _make_subsidy_with_leaf(
        db_session, "Subsidy-append-foreign-a", org_id=test_org.id, visible_to_user_id=test_user.id,
    )
    subsidy_b, cat_b = await _make_subsidy_with_leaf(
        db_session, "Subsidy-append-foreign-b", org_id=test_org.id, visible_to_user_id=test_user.id,
    )
    planned_b = await _make_planned_item(db_session, cat_b, "Позиция субсидии Б", quantity=Decimal("1"), unit_price=Decimal("100"), amount=Decimal("100"))
    wish, _existing_purchase = await _make_distributed_wish(db_session, subsidy_a, cat_a, test_user, test_org.id)

    items = [PlanToWishItemInput(feo_planned_item_id=planned_b.id, quantity=Decimal("1"), item_name="Позиция субсидии Б", price_source="plan")]

    with pytest.raises(HTTPException) as exc_info:
        await append_items_from_plan(db_session, test_user, wish.id, items)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_append_requires_auth(client, test_org, db_session, test_user):
    """POST /api/wishes/{id}/append-from-plan без токена — 401 (роутер уровня
    HTTP, не сервисный слой — проверяется через client, по образцу остальных
    401-тестов проекта)."""
    subsidy, cat = await _make_subsidy_with_leaf(
        db_session, "Subsidy-append-noauth", org_id=test_org.id, visible_to_user_id=test_user.id,
    )
    wish, _existing_purchase = await _make_distributed_wish(db_session, subsidy, cat, test_user, test_org.id)

    resp = await client.post(
        f"/api/wishes/{wish.id}/append-from-plan",
        json={"items": [{"feo_planned_item_id": 1, "quantity": "1"}]},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_move_last_item_out_of_append_purchase_deletes_it(db_session, test_user, test_org, client, auth_headers):
    """Перенос ПОСЛЕДНЕЙ позиции из колонки «Добавляем забытое» в другую
    закупку этой заявки удаляет опустевшую колонку сам (задача владельца, п.2)
    — HTTP-уровень, тот же роутер (POST /purchases/{id}/items/{id}/move), что
    и у обычного переноса между «сёстрами»."""
    subsidy, cat = await _make_subsidy_with_leaf(
        db_session, "Subsidy-append-move", org_id=test_org.id, visible_to_user_id=test_user.id,
    )
    planned = await _make_planned_item(db_session, cat, "Маркер", quantity=Decimal("10"), unit_price=Decimal("100"), amount=Decimal("1000"))
    wish, existing_purchase = await _make_distributed_wish(db_session, subsidy, cat, test_user, test_org.id)

    result = await append_items_from_plan(
        db_session, test_user, wish.id,
        [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=Decimal("1"), item_name="Маркер", price_source="plan")],
    )
    append_purchase_id = result["purchase_id"]
    pitem = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == append_purchase_id)
    )).scalars().first()
    assert pitem is not None

    resp = await client.post(
        f"/api/purchases/{append_purchase_id}/items/{pitem.id}/move",
        json={"target_purchase_id": existing_purchase.id},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_deleted"] is True
    assert body["source"] is None

    remaining = await db_session.get(Purchase, append_purchase_id)
    assert remaining is None
