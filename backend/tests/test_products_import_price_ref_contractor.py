"""Тесты apply_products_import: source_ref строки цены = ссылка на страницу
товара (не имя файла), contractor_id = контрагент магазина по seller_inn
строки (владелец, 26.10.2026, см. services/products_import_apply.py и
services/catalog_gala/stores.py). ПРАВИЛО №6 — резолвер контрагента один
(app.services.contractor_resolve.find_or_create_contractor), этот тест не
проверяет его внутреннюю логику повторно, только то, что apply_products_import
действительно его зовёт с правильным ИНН и переиспользует уже созданного
контрагента на второй строке того же магазина."""
import uuid

import pytest
from sqlalchemy import select

from app.models.contractor import Contractor
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.products_import_apply import apply_products_import

_UNIQ = "ТестGALAСсылкаКонтрагент_20261026"


def _uniq_name(suffix: str) -> str:
    return f"{_UNIQ} {suffix} {uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_new_product_price_ref_is_link_contractor_by_seller_inn(db_session, test_user):
    name = _uniq_name("Новый")
    url = "https://sima-land.ru/item/123456/"
    col_idx = {
        "name": 0, "price": 1, "link_url_1": 2, "source_url": 3, "seller_inn": 4,
    }
    data_rows = [(name, "150.50", url, url, "6679104850")]

    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="sima_land_catalog.gala.json", current_user=test_user,
    )
    assert result["created"] == 1, result

    product = (await db_session.execute(select(Product).where(Product.name == name))).scalar_one()
    assert product.price_source_ref == url
    assert product.price_source_contractor_id is not None

    contractor = await db_session.get(Contractor, product.price_source_contractor_id)
    assert contractor.inn == "6679104850"
    # Имя/ОГРН НЕ сверяем точной строкой (find_or_create_contractor находит
    # уже существующего контрагента по ИНН первым делом, и в реальной БД
    # этого стенда «Сима-ленд» уже есть с официальным полным наименованием
    # из ЕГРЮЛ — функция НЕ перезатирает его нашим "ООО ТД «Сима-ленд»",
    # это и есть правильное поведение, см. докстринг find_or_create_contractor)
    assert contractor.name

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 1
    assert hist[0].source_ref == url
    assert hist[0].contractor_id == contractor.id


@pytest.mark.asyncio
async def test_second_row_same_store_reuses_contractor_not_creates_second(db_session, test_user):
    url1 = "https://sima-land.ru/item/111/"
    url2 = "https://sima-land.ru/item/222/"
    col_idx = {"name": 0, "price": 1, "link_url_1": 2, "seller_inn": 3}
    name1 = _uniq_name("Товар1")
    name2 = _uniq_name("Товар2")
    data_rows = [
        (name1, "10", url1, "6679104850"),
        (name2, "20", url2, "6679104850"),
    ]

    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="sima_land_catalog.gala.json", current_user=test_user,
    )
    assert result["created"] == 2, result

    p1 = (await db_session.execute(select(Product).where(Product.name == name1))).scalar_one()
    p2 = (await db_session.execute(select(Product).where(Product.name == name2))).scalar_one()
    assert p1.price_source_contractor_id == p2.price_source_contractor_id

    count = (await db_session.execute(
        select(Contractor).where(Contractor.inn == "6679104850")
    )).scalars().all()
    assert len(count) == 1, "повторная строка того же магазина не должна создавать второго контрагента"


@pytest.mark.asyncio
async def test_unknown_domain_no_contractor_created(db_session, test_user):
    name = _uniq_name("НеизвестныйМагазин")
    url = "https://vseinstrumenti.ru/product/123/"
    col_idx = {"name": 0, "price": 1, "link_url_1": 2, "seller_inn": 3}
    # seller_inn не проставлен конвертером (домен неизвестен) — None в ячейке
    data_rows = [(name, "10", url, None)]

    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="catalog_goods_1010.gala.json", current_user=test_user,
    )
    assert result["created"] == 1, result
    product = (await db_session.execute(select(Product).where(Product.name == name))).scalar_one()
    assert product.price_source_ref == url
    assert product.price_source_contractor_id is None
