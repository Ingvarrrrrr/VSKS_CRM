"""Регресс: POST /api/products/bulk-from-purchase-items не возвращал тело
ответа (в routers/products_import.py::bulk_create_from_items не было
`return` после commit) — эндпоинт всегда отдавал null, хотя докстрока и
фронт (frontend/src/composables/items/useItemsCatalog.ts::bulkAddToCatalog)
ожидают {created, linked, errors}. Тест проверяет, что все три ключа
приходят в ответе.
"""
from decimal import Decimal

import pytest

from app.models.purchase_item import PurchaseItem
from app.models.product import Product


@pytest.mark.asyncio
async def test_bulk_from_purchase_items_returns_body(client, db_session, auth_headers, make_purchase_with_items):
    """Один непривязанный item (создаст Product) + один уже привязанный
    (пройдёт по ветке linked) — проверяем, что ответ содержит все три поля."""
    purchase = await make_purchase_with_items(items_count=2, item_total=Decimal("100"))

    existing_product = Product(name="Уже в каталоге")
    db_session.add(existing_product)
    await db_session.flush()

    items = (await db_session.execute(
        PurchaseItem.__table__.select().where(PurchaseItem.purchase_id == purchase.id)
    )).fetchall()
    item_ids = [row.id for row in items]
    assert len(item_ids) == 2

    # Привязываем первый item к каталогу заранее -> ветка "linked"
    first = await db_session.get(PurchaseItem, item_ids[0])
    first.product_id = existing_product.id
    await db_session.commit()

    resp = await client.post(
        "/api/products/bulk-from-purchase-items",
        json={"purchase_item_ids": item_ids},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data.keys()) == {"created", "linked", "errors"}
    assert data["created"] == 1
    assert data["linked"] == 1
    assert data["errors"] == []
