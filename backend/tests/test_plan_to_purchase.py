"""«Из плана — сразу в авансовый отчёт» (plan_to_purchase, владелец 30.09.2026):
создание Purchase(purchase_method='advance') напрямую из плановых позиций ФЭО,
без промежуточной заявки, БЕЗ обязательного выбора товара из каталога. Прямой
вызов сервисной функции (по образцу test_plan_to_wish.py) — роутер тонкий
(Правило №5).
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.plan_to_purchase import create_purchase_from_plan
from app.services.plan_to_wish import PlanToWishItemInput


async def _make_subsidy_with_leaf(db_session, name: str) -> tuple[Subsidy, FeoCategory]:
    # budget ненулевой (в отличие от test_plan_to_wish.py) — create_purchase
    # (в отличие от create_wish) сам гоняет _check_budget при создании закупки;
    # нулевой бюджет плодил бы побочное предупреждение "Превышен бюджет
    # субсидии", не относящееся к тому, что проверяют эти тесты.
    subsidy = Subsidy(name=name, year=2026, budget=1_000_000, status="approved", require_planned_dates=False)
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
async def test_create_advance_purchase_without_product_uses_plan_name_and_price(db_session, test_user):
    """Основной сценарий владельца: две плановые позиции, ни у одной НЕ выбран
    товар из каталога (product_id=None) — создание не должно требовать товара.
    item_name берётся из имени плановой позиции, цена — плановая (price_source
    'plan', как шлёт фронт по умолчанию для авансового режима)."""
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-advance-noproduct")
    planned1 = await _make_planned_item(db_session, cat, "Такси до склада", quantity=Decimal("3"), unit_price=Decimal("500"), amount=Decimal("1500"))
    planned2 = await _make_planned_item(db_session, cat, "Канцтовары разные", quantity=Decimal("1"), unit_price=Decimal("2200"), amount=Decimal("2200"))

    items = [
        PlanToWishItemInput(feo_planned_item_id=planned1.id, quantity=Decimal("2"), item_name="Такси до склада", price_source="plan"),
        PlanToWishItemInput(feo_planned_item_id=planned2.id, quantity=Decimal("1"), item_name="Канцтовары разные", price_source="plan"),
    ]

    result = await create_purchase_from_plan(db_session, test_user, _subsidy.id, None, items)

    assert result["items_count"] == 2
    assert result["warnings"] == []
    assert result["purchase_id"] is not None
    assert result["wish_id"] is not None  # авто-компаньон создан

    purchase = (await db_session.execute(select(Purchase).where(Purchase.id == result["purchase_id"]))).scalar_one()
    assert purchase.purchase_method == "advance"
    assert purchase.subsidy_id == _subsidy.id
    assert result["registry_number"] == purchase.registry_number
    assert purchase.registry_number

    purchase_items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id).order_by(PurchaseItem.id)
    )).scalars().all()
    assert len(purchase_items) == 2

    taxi_item = next(pi for pi in purchase_items if pi.feo_planned_item_id == planned1.id)
    # product_id НЕ был передан явно — но create_purchase (переиспользуется как
    # есть, см. докстринг plan_to_purchase.py) сам заводит Product по item_name,
    # когда product_id пуст: ровно то, что просил владелец («не требовало
    # заведения товара в БД» — руками заводить не нужно, система делает это
    # прозрачно). Поэтому product_id ЗАПОЛНЕН, но пользователь его не выбирал.
    assert taxi_item.product_id is not None
    auto_product = await db_session.get(Product, taxi_item.product_id)
    assert auto_product.name == "Такси до склада"
    assert taxi_item.item_name == "Такси до склада"
    assert taxi_item.unit_price == Decimal("500.00")  # плановая цена
    assert taxi_item.total_price == Decimal("1000.00")  # 2 x 500
    assert taxi_item.feo_planned_item_id == planned1.id
    assert taxi_item.feo_category_id == cat.id

    # Заявка-компаньон (Wish source='advance_report') с теми же позициями,
    # привязанными к плану (Правило №6 из задания — проверяем факт переиспользования
    # advance_wish_sync, а не копию его логики).
    wish = (await db_session.execute(select(Wish).where(Wish.id == result["wish_id"]))).scalar_one()
    assert wish.source == "advance_report"
    assert wish.subsidy_id == _subsidy.id
    wish_items = (await db_session.execute(select(WishItem).where(WishItem.wish_id == wish.id))).scalars().all()
    assert len(wish_items) == 2
    assert all(wi.feo_planned_item_id in (planned1.id, planned2.id) for wi in wish_items)


@pytest.mark.asyncio
async def test_create_advance_purchase_with_product_uses_catalog_name(db_session, test_user):
    """Товар из каталога — по-прежнему МОЖНО выбрать (необязательность не
    отбирает возможность), тогда item_name/цена берутся с товара как обычно."""
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-advance-withproduct")
    planned = await _make_planned_item(db_session, cat, "Мышь компьютерная", quantity=Decimal("5"), unit_price=Decimal("500"), amount=Decimal("2500"))

    product = Product(name="Мышь компьютерная Logitech", category="Оргтехника", price=Decimal("450"), unit="шт", is_active=True)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    items = [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=Decimal("2"), product_id=product.id, price_source="catalog")]
    result = await create_purchase_from_plan(db_session, test_user, _subsidy.id, "Купленные мыши", items)

    purchase_items = (await db_session.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == result["purchase_id"]))).scalars().all()
    assert len(purchase_items) == 1
    assert purchase_items[0].product_id == product.id
    assert purchase_items[0].item_name == "Мышь компьютерная Logitech"
    assert purchase_items[0].unit_price == Decimal("450.00")

    purchase = (await db_session.execute(select(Purchase).where(Purchase.id == result["purchase_id"]))).scalar_one()
    assert purchase.item_name == "Купленные мыши"  # явный title побеждает


@pytest.mark.asyncio
async def test_create_advance_purchase_409_when_over_residual(db_session, test_user):
    """Тот же жёсткий гейт остатка плана, что и у «в заявку» — переиспользует
    build_items_from_plan, второй расчёт не заводит (Правило №6)."""
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-advance-overresidual")
    planned = await _make_planned_item(db_session, cat, "Тонер для принтера", quantity=Decimal("5"), unit_price=Decimal("2000"), amount=Decimal("10000"))

    purchase = Purchase(status="plan_schedule", item_type="товар", item_name="Тонер", registry_number="РЕЕ-2026-00961")
    db_session.add(purchase)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=purchase.id, item_name="Тонер для принтера", quantity=Decimal("4"), unit="шт",
        unit_price=Decimal("2000"), total_price=Decimal("8000"), feo_planned_item_id=planned.id,
    ))
    await db_session.commit()

    items = [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=Decimal("3"), item_name="Тонер для принтера", price_source="plan")]

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await create_purchase_from_plan(db_session, test_user, _subsidy.id, None, items)

    assert exc_info.value.status_code == 409
    assert "остаток 1" in exc_info.value.detail and "запрошено 3" in exc_info.value.detail
