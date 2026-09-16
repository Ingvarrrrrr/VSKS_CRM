"""Владелец, 2026-09-16, п.2/E: колонка «Дата цены» в импорте товаров —
заполнена → цена в истории пишется этой датой; пусто → датой загрузки файла.
Каждая импортированная цена — запись ProductPriceHistory(source='import',
source_ref=имя файла)."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.products_import_apply import apply_products_import
from app.services.products_import_map import suggest_products_column_mapping


def test_price_date_header_recognized():
    col_idx = suggest_products_column_mapping(["Наименование", "Цена", "Дата цены"])
    assert col_idx["price_date"] == 2

    col_idx2 = suggest_products_column_mapping(["Наименование", "Цена", "Дата обновления цены"])
    assert col_idx2["price_date"] == 2

    col_idx3 = suggest_products_column_mapping(["Наименование", "Цена", "Цена на дату"])
    assert col_idx3["price_date"] == 2


@pytest.mark.asyncio
async def test_import_new_product_with_explicit_price_date(db_session, test_user):
    col_idx = {"name": 0, "price": 1, "price_date": 2}
    data_rows = [("Новый товар с датой цены", "1000", "01.09.2026")]

    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="test_price_date.xlsx", current_user=test_user,
    )
    assert result["created"] == 1
    assert not result["errors"]

    product = (await db_session.execute(
        select(Product).where(Product.name == "Новый товар с датой цены")
    )).scalar_one()
    assert product.price == Decimal("1000")

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 1
    assert hist[0].source == "import"
    assert hist[0].source_ref == "test_price_date.xlsx"
    assert hist[0].collected_at == date(2026, 9, 1)


@pytest.mark.asyncio
async def test_import_new_product_without_price_date_uses_upload_date(db_session, test_user):
    col_idx = {"name": 0, "price": 1, "price_date": 2}
    data_rows = [("Новый товар без даты цены", "500", None)]

    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="test_no_date.xlsx", current_user=test_user,
    )
    assert result["created"] == 1

    product = (await db_session.execute(
        select(Product).where(Product.name == "Новый товар без даты цены")
    )).scalar_one()

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 1
    assert hist[0].collected_at == date.today()


@pytest.mark.asyncio
async def test_import_existing_product_price_change_uses_price_date(db_session, test_user):
    product = Product(name="Товар для повторного импорта", category="Прочее", price=Decimal("100"))
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    col_idx = {"name": 0, "price": 1, "price_date": 2}
    data_rows = [("Товар для повторного импорта", "150", "15.08.2026")]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="reimport.xlsx", current_user=test_user,
    )
    assert result["updated"] == 1

    await db_session.refresh(product)
    assert product.price == Decimal("150")

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 1
    assert hist[0].source == "import"
    assert hist[0].collected_at == date(2026, 8, 15)
