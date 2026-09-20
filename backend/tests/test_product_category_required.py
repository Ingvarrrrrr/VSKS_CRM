"""Tests for products.category defaulting (владелец, 2026-09-20).

Было (D-03): category — обязательное поле, пусто/None → 422. На практике
это ломало ручное добавление товара из FullProductDialog.vue: пользователь
не всегда знает категорию сразу, POST падал 422, фронт глотал ошибку generic
текстом («Ошибка при добавлении товара»).

Стало: category опциональна на входе (ProductCreate.category: Optional[str]);
пусто/None → роутер (app/routers/products.py) подставляет
app.models.product.DEFAULT_PRODUCT_CATEGORY ('Прочее') — та же константа, что
и дефолт колонки Product.category в БД, не два литерала (ПРАВИЛО №6).
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.product_price_history import ProductPriceHistory


@pytest.mark.asyncio
async def test_create_product_without_category_defaults_to_default_category(client: AsyncClient, auth_headers):
    """Отсутствующее поле category → 201, категория подставлена дефолтом."""
    resp = await client.post(
        "/api/products/",
        headers=auth_headers,
        json={"name": "Test product", "item_kind": "товар"},
    )
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["category"] == "Прочее"


@pytest.mark.asyncio
async def test_create_product_with_empty_category_defaults_to_default_category(client: AsyncClient, auth_headers):
    """Пустая строка category → 201, категория подставлена дефолтом (не 422)."""
    resp = await client.post(
        "/api/products/",
        headers=auth_headers,
        json={"name": "Test empty category", "category": "", "item_kind": "товар"},
    )
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["category"] == "Прочее"


@pytest.mark.asyncio
async def test_create_product_with_category_returns_200_or_201(client: AsyncClient, auth_headers):
    """Явно заданная категория — используется как есть, не подменяется дефолтом."""
    resp = await client.post(
        "/api/products/",
        headers=auth_headers,
        json={"name": "Test Электроника", "category": "Электроника", "item_kind": "товар"},
    )
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["category"] == "Электроника"


@pytest.mark.asyncio
async def test_create_product_with_price_sets_price_updated_at(client: AsyncClient, auth_headers, db_session):
    """Координатор, 2026-09-20 (добивка): POST с ценой проходил (201), но
    create_product клал price напрямую в Product(**data), минуя
    actualize_product_price — price_updated_at оставался null (та же болезнь,
    что чинилась в импорте ТЗ). Теперь цена идёт через
    _actualize_price_from_form → actualize_product_price: price_updated_at
    заполнен, price_source='manual' (без price_links), и есть строка в
    product_price_history."""
    resp = await client.post(
        "/api/products/",
        headers=auth_headers,
        json={"name": "Test manual price product", "price": 123.45, "item_kind": "товар"},
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["price_updated_at"] is not None, "price_updated_at остался null после ручного добавления товара с ценой"
    assert body["price_source"] == "manual"

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == body["id"])
    )).scalars().all()
    assert len(hist) == 1
    assert hist[0].source == "manual"
    assert hist[0].collected_at is not None
