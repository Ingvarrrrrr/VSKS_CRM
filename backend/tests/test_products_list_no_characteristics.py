"""GET /api/products/ не отдаёт characteristics (defer) и, что важнее,
не портит их в БД (баг владельца 26.10.2026): характеристики грузились
с defer(), а потом в list_products им явно присваивали None обычным
`p.characteristics = None` на ORM-объекте — SQLAlchemy помечал объект
dirty, и autoflush перед следующим запросом (_attach_price_stats) слал
UPDATE products SET characteristics=NULL на каждый товар списка (53 тыс.
на проде). Фикс — set_committed_value вместо присваивания: объект
остаётся clean, UPDATE не шлётся, characteristics в БД не трогаются."""
import pytest
from sqlalchemy import select

from app.models.product import Product


@pytest.mark.asyncio
async def test_list_products_hides_characteristics_but_does_not_wipe_db(
    client, db_session, auth_headers,
):
    product = Product(
        name="Товар с характеристиками",
        characteristics={"Цвет": "белый", "Материал": "пластик"},
    )
    db_session.add(product)
    await db_session.commit()
    product_id = product.id

    resp = await client.get("/api/products/", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    item = next(p for p in data if p["id"] == product_id)
    # В ответе списка characteristics не отдаются (намеренно, defer).
    assert item.get("characteristics") is None

    # Ключевая проверка: в БД характеристики НЕ затёрлись побочным UPDATE.
    # Свежий запрос новой сессией к той же записи — session.dirty проверять
    # бессмысленно (db_session из фикстуры живёт в своей транзакции), поэтому
    # проверяем фактическое значение в БД после эндпойнта.
    fresh = (await db_session.execute(
        select(Product.characteristics).where(Product.id == product_id)
    )).scalar_one()
    assert fresh == {"Цвет": "белый", "Материал": "пластик"}


@pytest.mark.asyncio
async def test_list_products_requires_auth(client):
    resp = await client.get("/api/products/")
    assert resp.status_code == 401
