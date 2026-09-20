"""Задача 2 (владелец, 2026-09-20): «Позиции заявки с фото/ценой на сервере,
вместо полного каталога на фронте».

GET /api/wishes/{id} — карточка заявки отдаёт у каждой позиции has_photo/
photo_url/price_freshness товара каталога (app.services.wish_serializers.
_attach_item_product_snapshot, источник значений — app.services.product_snapshot.
build_product_snapshot, единственная функция, Правило №6).

GET /api/products/?ids=a,b — точечная догрузка карточек по id (app.routers.
products.py::list_products), фронту больше не нужно грузить весь каталог,
чтобы показать снимок карточки позиции заявки.
"""
from decimal import Decimal
from datetime import datetime

import pytest

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.product import Product
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory


async def _make_wish_with_items(db_session, test_org, test_user, *, with_photo_product, plain_name_item):
    subsidy = Subsidy(name=f"TestSubsidy-{id(db_session)}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    feo_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Прочее")
    db_session.add(feo_cat)
    await db_session.flush()

    product = Product(
        name=with_photo_product, category="Оргтехника", price=Decimal("1000"),
        photo_size=12345, photo_mime="image/jpeg",  # bytea "cached" (no real bytes needed for this test)
        price_updated_at=datetime.utcnow(), price_source="manual", is_active=True,
        description="Тестовое описание товара для ТЗ", description_44fz="Интервал характеристик 44-ФЗ",
    )
    db_session.add(product)
    await db_session.flush()

    w = Wish(
        org_id=test_org.id, title="Заявка со снимком товара", status="draft",
        created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=feo_cat.id,
    )
    db_session.add(w)
    await db_session.flush()

    item_by_id = WishItem(
        wish_id=w.id, product_id=product.id, item_name=with_photo_product,
        quantity=1, unit_price=1000, total_price=1000,
    )
    item_by_name = WishItem(
        wish_id=w.id, product_id=None, item_name=plain_name_item,
        quantity=2, unit_price=500, total_price=1000,
    )
    db_session.add_all([item_by_id, item_by_name])
    await db_session.commit()
    await db_session.refresh(w)
    return w, product, item_by_id, item_by_name


@pytest.mark.asyncio
async def test_get_wish_attaches_item_product_snapshot(client, db_session, test_org, test_user, auth_headers):
    import uuid
    suffix = uuid.uuid4().hex[:8]
    name = f"Принтер лазерный тест-{suffix}"

    w, product, item_by_id, item_by_name = await _make_wish_with_items(
        db_session, test_org, test_user, with_photo_product=name, plain_name_item="Что-то без товара",
    )

    resp = await client.get(f"/api/wishes/{w.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    items_by_id = {it["id"]: it for it in data["items"]}
    matched = items_by_id[item_by_id.id]
    assert matched["product_id"] == product.id
    assert matched["has_photo"] is True
    assert matched["photo_url"] == f"/api/products/{product.id}/photo"
    assert matched["description"] == "Тестовое описание товара для ТЗ"
    assert matched["description_44fz"] == "Интервал характеристик 44-ФЗ"
    assert matched["price_source"] == "manual"
    assert matched["price_freshness"] is not None
    assert matched["price_freshness"]["reason"] == "ok"

    unmatched = items_by_id[item_by_name.id]
    assert unmatched["product_id"] is None
    assert unmatched["has_photo"] is None


@pytest.mark.asyncio
async def test_get_wish_item_matches_by_exact_normalized_name(client, db_session, test_org, test_user, auth_headers):
    """Позиция БЕЗ product_id, но с именем, точно совпадающим (после normalize)
    с ровно одним товаром каталога — снимок подставляется по имени."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    name = f"Мышь беспроводная тест-{suffix}"

    subsidy = Subsidy(name=f"TestSubsidy-{id(db_session)}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    feo_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Прочее")
    db_session.add(feo_cat)
    await db_session.flush()

    product = Product(name=name, category="Оргтехника", price=Decimal("700"), is_active=True)
    db_session.add(product)
    await db_session.flush()

    w = Wish(
        org_id=test_org.id, title="Заявка — сопоставление по имени", status="draft",
        created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=feo_cat.id,
    )
    db_session.add(w)
    await db_session.flush()
    item = WishItem(wish_id=w.id, product_id=None, item_name=name.upper() + "  ", quantity=1, unit_price=700, total_price=700)
    db_session.add(item)
    await db_session.commit()

    resp = await client.get(f"/api/wishes/{w.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    out_item = next(it for it in data["items"] if it["id"] == item.id)
    assert out_item["product_id"] == product.id
    assert out_item["price_freshness"]["reason"] == "never"  # price_updated_at не задан


@pytest.mark.asyncio
async def test_list_products_filters_by_ids(client, db_session, auth_headers):
    p1 = Product(name="Товар A для ids-теста", category="Прочее", is_active=True)
    p2 = Product(name="Товар B для ids-теста", category="Прочее", is_active=True)
    p3 = Product(name="Товар C для ids-теста (не запрошен)", category="Прочее", is_active=True)
    db_session.add_all([p1, p2, p3])
    await db_session.commit()
    await db_session.refresh(p1)
    await db_session.refresh(p2)
    await db_session.refresh(p3)

    resp = await client.get(f"/api/products/?ids={p1.id},{p2.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    ids_returned = {p["id"] for p in data}
    assert ids_returned == {p1.id, p2.id}


@pytest.mark.asyncio
async def test_list_products_ids_invalid_format_422(client, auth_headers):
    resp = await client.get("/api/products/?ids=abc,1", headers=auth_headers)
    assert resp.status_code == 422, resp.text
