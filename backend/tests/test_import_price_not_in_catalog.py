# -*- coding: utf-8 -*-
"""Решение владельца, 14.10.2026: цена позиции из загружаемого файла (план
закупок / ТЗ закупки / позиции закупки) и цена позиции закупки — это цена
ЭТОЙ субсидии/закупки, она живёт в самой позиции (purchase_items.unit_price /
плановой позиции). В товар каталога (products.price и product_price_history)
она НЕ пишется.

Разрешённые писатели цены каталога (НЕ меняются этим тестом):
- ручное «Добавить цену» (manual/kp/monitoring, routers/products_price.py);
- договор прошлой закупки (source='contract', purchase_transition_core.py);
- загрузка самого каталога товаров из Excel (products_import_apply.py —
  покрыт test_products_import_price_date.py, тут НЕ трогаем);
- commercial_requests (КП).

Этот файл покрывает три места, у которых запись цены в каталог убрана:
(а) _apply_import_to_existing_product — дозаполнение уже найденного товара;
(б) _upsert_product_to_catalog — создание нового товара импортом позиций;
(в) purchase_create_core.insert_purchase_with_items — товар "на лету" при
    создании закупки с новой позицией без product_id (тот же блок
    продублирован в routers/purchases.py::update_purchase — Правило №6,
    дедуп не входит в эту правку, см. отчёт).

Гоняется по одному узлу за вызов pytest, как и соседний
test_items_import_catalog_dedup.py (флейк pytest-asyncio «different loop»).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.items_import_catalog import (
    _apply_import_to_existing_product,
    _upsert_product_to_catalog,
)

_UNIQ = "ТестЦенаНеВКаталог_20261014"


@pytest.mark.asyncio
async def test_apply_import_to_existing_product_does_not_overwrite_manual_price(db_session):
    """Товар с ручной ценой (manual, 500) — импорт позиции с unit_price=999
    дозаполняет пустые поля, но products.price остаётся 500 и новых строк
    product_price_history не появляется."""
    p = Product(
        name=f"{_UNIQ} Manual", category="Прочее",
        price=Decimal("500"), price_source="manual",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    await _apply_import_to_existing_product(db_session, p, unit_price=Decimal("999"))
    await db_session.refresh(p)

    assert p.price == Decimal("500"), "цена закупки перетёрла ручную цену каталога"
    assert p.price_source == "manual"

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == p.id)
    )).scalars().all()
    assert hist == [], "импорт позиции не должен писать строку в product_price_history"


@pytest.mark.asyncio
async def test_upsert_new_product_from_import_has_no_price(db_session):
    """Новый товар, заведённый _upsert_product_to_catalog при импорте позиций
    (unit_price=999) — товар создан, но price is None, истории цены нет."""
    name = f"{_UNIQ} New {uuid.uuid4().hex[:8]}"
    pid = await _upsert_product_to_catalog(db_session, name, "товар", Decimal("999"))

    p = (await db_session.execute(select(Product).where(Product.id == pid))).scalar_one()
    assert p.price is None, "новый товар из импорта позиций получил цену строки"
    assert p.price_source is None

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == pid)
    )).scalars().all()
    assert hist == []


@pytest.mark.asyncio
async def test_purchase_create_with_new_item_does_not_set_catalog_price(
    client, auth_headers, db_session,
):
    """Создание закупки с новой позицией без product_id (путь
    purchase_create_core.insert_purchase_with_items, вызывается из
    routers/purchases.py::create_purchase) — товар "на лету" заводится без
    price (раньше: Product(price=d.get("unit_price"), ...))."""
    item_name = f"{_UNIQ} Товар на лету {uuid.uuid4().hex[:8]}"
    payload = {
        "purchase_method": "advance",
        "subject": "Тест — цена не пишется в каталог (14.10)",
        "items": [
            {
                "item_name": item_name,
                "item_type": "товар",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 1234,
                "total_price": 1234,
            }
        ],
    }
    resp = await client.post("/api/purchases/", json=payload, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text

    product = (await db_session.execute(
        select(Product).where(Product.name == item_name.strip())
    )).scalar_one()
    assert product.price is None, "товар, заведённый из позиции закупки, получил цену в каталог"
