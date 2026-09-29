"""DELETE /api/products/{id} — блокировка удаления товара, стоящего в позиции
закупки (боевая жалоба владельца, 2026-09-29: DELETE /api/products/4280 падал
500 ForeignKeyViolationError вместо понятного отказа).

Проверяем: товар в позиции закупки -> 409 с номером закупки в detail, товар
без связей -> удаляется вместе со своей историей цен (app/services/
product_delete_impact.py — собственные данные товара CASCADE, бизнес-
документы блокируют, Правило №6)."""
from decimal import Decimal
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish
from app.models.wish_item import WishItem


@pytest.mark.asyncio
async def test_delete_product_blocked_by_purchase_item(client, db_session, auth_headers):
    product = Product(name="Петля спасательная тест", category="Прочее", is_active=True)
    db_session.add(product)
    await db_session.flush()

    purchase = Purchase(purchase_number=921, item_name="Петля спасательная тест", status="plan_schedule")
    db_session.add(purchase)
    await db_session.flush()

    item = PurchaseItem(
        purchase_id=purchase.id, product_id=product.id, item_name="Петля спасательная тест",
        quantity=1, unit_price=Decimal("100"), total_price=Decimal("100"),
    )
    db_session.add(item)
    await db_session.commit()

    resp = await client.delete(f"/api/products/{product.id}", headers=auth_headers)
    assert resp.status_code == 409, resp.text
    detail = resp.json()["details"]
    assert resp.json()["code"] == "PRODUCT_HAS_DEPENDENTS"
    assert "921" in detail["message"], detail["message"]
    assert detail["impact"]["purchases"]["count"] == 1
    assert detail["impact"]["purchases"]["items"][0]["id"] == purchase.id

    # Товар не удалён — виден в каталоге как раньше.
    still_there = (await db_session.execute(select(Product).where(Product.id == product.id))).scalar_one_or_none()
    assert still_there is not None


@pytest.mark.asyncio
async def test_delete_product_blocked_by_wish_item(client, db_session, test_org, test_user, auth_headers):
    product = Product(name="Товар в заявке тест", category="Прочее", is_active=True)
    db_session.add(product)
    await db_session.flush()

    wish = Wish(org_id=test_org.id, title="Заявка-блокер теста", status="draft", created_by=test_user.id)
    db_session.add(wish)
    await db_session.flush()

    wish_item = WishItem(wish_id=wish.id, product_id=product.id, item_name="Товар в заявке тест", quantity=1, unit_price=10, total_price=10)
    db_session.add(wish_item)
    await db_session.commit()

    resp = await client.delete(f"/api/products/{product.id}", headers=auth_headers)
    assert resp.status_code == 409, resp.text
    detail = resp.json()["details"]
    assert resp.json()["code"] == "PRODUCT_HAS_DEPENDENTS"
    assert detail["impact"]["wishes"]["count"] == 1


@pytest.mark.asyncio
async def test_delete_unused_product_succeeds_and_cleans_price_history(client, db_session, auth_headers):
    product = Product(
        name="Неиспользуемый товар тест", category="Прочее", is_active=True,
        price=Decimal("500"), price_updated_at=datetime.utcnow(), price_source="manual",
    )
    db_session.add(product)
    await db_session.flush()
    hist = ProductPriceHistory(product_id=product.id, price=Decimal("500"), source="manual")
    db_session.add(hist)
    await db_session.commit()
    product_id = product.id

    resp = await client.delete(f"/api/products/{product_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    gone = (await db_session.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    assert gone is None
    hist_gone = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product_id)
    )).scalars().all()
    assert hist_gone == []
