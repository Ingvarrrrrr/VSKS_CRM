"""«Из плана — в заявку» (plan-to-wish, сессия 2026-09-20).

Кандидаты (POST /feo-planned-items/plan-to-wish/candidates) и создание заявки
(POST /feo-planned-items/plan-to-wish/create) — тестируются через прямой вызов
сервисных функций app.services.plan_to_wish (по образцу
test_feo_product_hint_category_match.py — прямой вызов роутер-функции с
db_session/test_user, без HTTP-клиента), т.к. вся интересующая логика лежит в
сервисном слое, а роутер — тонкая обёртка (Правило №5).
"""
from decimal import Decimal

import pytest

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.plan_to_wish import (
    PlanToWishItemInput,
    build_plan_to_wish_candidates,
    create_wish_from_plan,
)


async def _make_subsidy_with_leaf(db_session, name: str) -> tuple[Subsidy, FeoCategory]:
    """Утверждённая (status='approved') субсидия с одной листовой категорией ФЭО —
    create_wish (вызывается изнутри create_wish_from_plan) отклоняет привязку к
    черновой субсидии (assert_subsidy_approved_for_binding), поэтому тестовая
    субсидия обязана быть 'approved', а не полагаться на server_default='draft'."""
    subsidy = Subsidy(name=name, year=2026, budget=0, status="approved", require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=3, name="Прочее")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(subsidy)
    await db_session.refresh(cat)
    return subsidy, cat


async def _make_planned_item(db_session, cat: FeoCategory, name: str, quantity=None, unit_price=None, amount=None, unit="шт") -> FeoPlannedItem:
    item = FeoPlannedItem(
        feo_category_id=cat.id, name=name, quantity=quantity, unit_price=unit_price,
        amount=amount, unit=unit, is_active=True,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest.mark.asyncio
async def test_candidates_exact_name_match(db_session, test_user):
    """Тесты гоняются на общем dev-каталоге (products — единый справочник, см.
    память проекта) — имя намеренно с уникальным суффиксом (uuid), чтобы
    случайно не столкнуться по стемам с реальным товаром из живой БД (иначе
    'exact' может уйти чужому кандидату с тем же совпадением по одному слову)."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    name = f"Огнетушитель ОП-5 тест-{suffix}"

    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-exact")
    planned = await _make_planned_item(db_session, cat, name, quantity=Decimal("10"), unit_price=Decimal("1000"), amount=Decimal("10000"))

    product = Product(name=name, category="Прочее", price=Decimal("950"), is_active=True)
    db_session.add(product)
    await db_session.commit()

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)

    assert len(result) == 1
    row = result[0]
    assert row["planned_item_id"] == planned.id
    assert row["feo_category_id"] == cat.id
    assert row["exact"] is not None, f"expected exact match, got: {row}"
    assert row["exact"]["product_id"] == product.id
    assert row["exact"]["score"] >= 0.95
    assert row["exact"]["product_type"] == product.product_type  # None here, field present
    assert row["exact"]["unit"] == product.unit


@pytest.mark.asyncio
async def test_candidates_by_type_match(db_session, test_user):
    """«Принтер» при товарах с product_type «принтер» (разные названия) → by_type,
    а не exact/by_name (имена совсем другие — score по имени низкий).

    Имя плановой позиции — «Принтер тест-{uuid}» (не голое «Принтер»): общий
    dev-каталог реально содержит десятки товаров со словом «принтер»/«принтера»
    в названии (расходники/запчасти) — однословный запрос совпадает с ЛЮБЫМ из
    них по стему с coverage=1.0 и мог случайно попасть в exact/by_name. Второе
    слово с уникальным суффиксом гарантирует, что ни один реальный товар не
    наберёт полное покрытие по НАЗВАНИЮ — но word-токен «принтер» (>=4 симв.)
    всё равно попадает в match_targets для by_type (см. build_plan_to_wish_candidates)."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    name = f"Принтер тест-{suffix}"

    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-type")
    planned = await _make_planned_item(db_session, cat, name, quantity=Decimal("2"), unit_price=Decimal("15000"), amount=Decimal("30000"))

    p1 = Product(name=f"HP LaserJet M140w {suffix}", product_type="Принтер", category="Оргтехника", price=Decimal("14000"), is_active=True)
    p2 = Product(name=f"Canon i-SENSYS LBP6030 {suffix}", product_type="принтер", category="Оргтехника", price=Decimal("13000"), is_active=True)
    unrelated = Product(name=f"Сканер Epson {suffix}", product_type="Сканер", category="Оргтехника", price=Decimal("9000"), is_active=True)
    db_session.add_all([p1, p2, unrelated])
    await db_session.commit()

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    row = result[0]

    assert row["exact"] is None
    by_type_ids = {c["product_id"] for c in row["by_type"]}
    assert p1.id in by_type_ids and p2.id in by_type_ids, f"expected both printers in by_type, got: {row['by_type']}"
    assert unrelated.id not in by_type_ids


@pytest.mark.asyncio
async def test_candidates_residual_excludes_draft_wish_but_not_plan_schedule_purchase(db_session, test_user, test_org):
    """Остаток плановой позиции (used_quantity/residual_quantity) учитывает
    PurchaseItem, привязанный к закупке в plan_schedule, но НЕ учитывает
    черновую заявку (WishItem с тем же feo_planned_item_id, без закупки) —
    ровно правило planned_item_consumption (owner, 2026-08-17)."""
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-residual")
    planned = await _make_planned_item(db_session, cat, "Бумага А4", quantity=Decimal("10"), unit_price=Decimal("300"), amount=Decimal("3000"), unit="упак")

    purchase = Purchase(status="plan_schedule", item_type="товар", item_name="Бумага")
    db_session.add(purchase)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=purchase.id, item_name="Бумага А4", quantity=Decimal("3"), unit="упак",
        unit_price=Decimal("300"), total_price=Decimal("900"), feo_planned_item_id=planned.id,
    )
    db_session.add(pi)

    # Черновая заявка на ту же плановую позицию — НЕ должна уменьшать остаток.
    draft_wish = Wish(org_id=test_org.id, title="Черновик", status="draft", created_by=test_user.id)
    db_session.add(draft_wish)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=draft_wish.id, item_name="Бумага А4", quantity=Decimal("5"), unit="упак",
        unit_price=Decimal("300"), total_price=Decimal("1500"), feo_planned_item_id=planned.id,
    ))
    await db_session.commit()

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    row = result[0]

    assert row["used_quantity"] == Decimal("3"), f"expected used_quantity=3 (only the purchase), got {row['used_quantity']}"
    assert row["residual_quantity"] == Decimal("7"), f"expected residual=10-3=7, got {row['residual_quantity']}"
    assert len(row["linked_purchases"]) == 1
    assert row["linked_purchases"][0]["purchase_id"] == purchase.id
    assert row["linked_purchases"][0]["status"] == "plan_schedule"
    assert row["linked_purchases"][0]["quantity"] == 3.0


@pytest.mark.asyncio
async def test_candidates_linked_purchase_initiator_name(db_session, test_admin_user):
    """linked_purchases[].initiator_name — service_note_by, если задан, иначе assigned_user_id."""
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-initiator")
    planned = await _make_planned_item(db_session, cat, "Стулья офисные", quantity=Decimal("5"), unit_price=Decimal("2000"), amount=Decimal("10000"))

    purchase = Purchase(
        status="plan_schedule", item_type="товар", item_name="Стулья",
        service_note_by=test_admin_user.id,
    )
    db_session.add(purchase)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=purchase.id, item_name="Стулья офисные", quantity=Decimal("2"), unit="шт",
        unit_price=Decimal("2000"), total_price=Decimal("4000"), feo_planned_item_id=planned.id,
    ))
    await db_session.commit()

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    linked = result[0]["linked_purchases"]
    assert len(linked) == 1
    assert linked[0]["initiator_user_id"] == test_admin_user.id
    assert linked[0]["initiator_name"] == test_admin_user.full_name


@pytest.mark.asyncio
async def test_create_wish_two_items_catalog_and_manual(db_session, test_user):
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-create")
    planned1 = await _make_planned_item(db_session, cat, "Мышь компьютерная", quantity=Decimal("10"), unit_price=Decimal("500"), amount=Decimal("5000"))
    planned2 = await _make_planned_item(db_session, cat, "Клавиатура", quantity=Decimal("10"), unit_price=Decimal("1500"), amount=Decimal("15000"))

    product = Product(name="Мышь компьютерная Logitech", category="Оргтехника", price=Decimal("450"), unit="шт", is_active=True)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    items = [
        PlanToWishItemInput(feo_planned_item_id=planned1.id, quantity=Decimal("2"), product_id=product.id, price_source="catalog"),
        PlanToWishItemInput(feo_planned_item_id=planned2.id, quantity=Decimal("1"), item_name="Клавиатура механическая", price_source="plan"),
    ]

    result = await create_wish_from_plan(db_session, test_user, _subsidy.id, None, items)

    assert result["items_count"] == 2
    assert _subsidy.name in result["title"]
    assert result["warnings"] == []

    from sqlalchemy import select
    wish = (await db_session.execute(select(Wish).where(Wish.id == result["wish_id"]))).scalar_one()
    assert wish.status == "draft"
    assert wish.subsidy_id == _subsidy.id

    wish_items = (await db_session.execute(select(WishItem).where(WishItem.wish_id == wish.id).order_by(WishItem.id))).scalars().all()
    assert len(wish_items) == 2

    mouse_item = next(wi for wi in wish_items if wi.feo_planned_item_id == planned1.id)
    assert mouse_item.product_id == product.id
    assert mouse_item.item_name == "Мышь компьютерная Logitech"
    assert mouse_item.unit_price == Decimal("450.00")  # цена из каталога
    assert mouse_item.total_price == Decimal("900.00")  # 2 x 450
    assert mouse_item.feo_category_id == cat.id

    kb_item = next(wi for wi in wish_items if wi.feo_planned_item_id == planned2.id)
    assert kb_item.product_id is None
    assert kb_item.item_name == "Клавиатура механическая"
    assert kb_item.unit_price == Decimal("1500.00")  # плановая цена (price_source='plan')
    assert kb_item.total_price == Decimal("1500.00")

    # Обе позиции — одна и та же категория → wish.feo_category_id проставлена
    assert wish.feo_category_id == cat.id


@pytest.mark.asyncio
async def test_create_wish_price_fallback_when_catalog_price_missing(db_session, test_user):
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-fallback")
    planned = await _make_planned_item(db_session, cat, "Флешка USB", quantity=Decimal("20"), unit_price=Decimal("400"), amount=Decimal("8000"))

    product = Product(name="Флешка USB Kingston 32GB", category="Оргтехника", price=None, is_active=True)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    items = [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=Decimal("3"), product_id=product.id, price_source="catalog")]
    result = await create_wish_from_plan(db_session, test_user, _subsidy.id, "Тест fallback", items)

    assert any("плановая цена" in w for w in result["warnings"]), result["warnings"]

    from sqlalchemy import select
    wi = (await db_session.execute(select(WishItem).where(WishItem.wish_id == result["wish_id"]))).scalars().first()
    assert wi.unit_price == Decimal("400.00")  # плановая цена как fallback
    assert wi.total_price == Decimal("1200.00")  # 3 x 400


@pytest.mark.asyncio
async def test_create_wish_warns_when_over_residual(db_session, test_user):
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-overresidual")
    planned = await _make_planned_item(db_session, cat, "Тонер для принтера", quantity=Decimal("5"), unit_price=Decimal("2000"), amount=Decimal("10000"))

    purchase = Purchase(status="plan_schedule", item_type="товар", item_name="Тонер", purchase_number=777)
    db_session.add(purchase)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=purchase.id, item_name="Тонер для принтера", quantity=Decimal("4"), unit="шт",
        unit_price=Decimal("2000"), total_price=Decimal("8000"), feo_planned_item_id=planned.id,
    ))
    await db_session.commit()

    # residual = 5 - 4 = 1; запрашиваем 3 → предупреждение
    items = [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=Decimal("3"), item_name="Тонер для принтера", price_source="plan")]
    result = await create_wish_from_plan(db_session, test_user, _subsidy.id, "Тест превышения", items)

    assert result["items_count"] == 1
    assert any("остаток 1" in w and "запрошено 3" in w for w in result["warnings"]), result["warnings"]
    assert any("777" in w for w in result["warnings"]), result["warnings"]


@pytest.mark.asyncio
async def test_create_wish_422_foreign_subsidy(db_session, test_user):
    _subsidy_a, cat_a = await _make_subsidy_with_leaf(db_session, "Subsidy-A")
    _subsidy_b, _cat_b = await _make_subsidy_with_leaf(db_session, "Subsidy-B")
    planned = await _make_planned_item(db_session, cat_a, "Позиция субсидии A", quantity=Decimal("1"), unit_price=Decimal("100"), amount=Decimal("100"))

    items = [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=Decimal("1"), item_name="Позиция субсидии A", price_source="plan")]

    with pytest.raises(Exception) as exc_info:
        await create_wish_from_plan(db_session, test_user, _subsidy_b.id, None, items)

    from fastapi import HTTPException
    assert isinstance(exc_info.value, HTTPException)
    assert exc_info.value.status_code == 422
