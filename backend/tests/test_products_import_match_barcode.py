"""Критерий (0.25) сопоставления строки импорта — штрихкод (решение
владельца, 27.10.2026: EAN-13/EAN-8/UPC-12/GTIN-14 — главный ключ сведения
одной карточки товара из разных магазинов). См. докстринг
app/services/products_import_match.py и app/services/products_import_match_
barcode.py. Тот же стиль проверки, что у test_products_import_match.py
(brand_article)."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_price_history import ProductPriceHistory
from app.services.contractor_resolve import find_or_create_contractor
from app.services.products_import_apply import apply_products_import

_UNIQ = "ТестШтрихкод_20261027"
_VALID_EAN13 = "4006381333931"  # см. test_barcodes.py


def _uniq_name(suffix: str) -> str:
    return f"{_UNIQ} {suffix} {uuid.uuid4().hex[:8]}"


async def _count_by_name(db_session, name: str) -> int:
    rows = (await db_session.execute(select(Product).where(Product.name == name))).scalars().all()
    return len(rows)


@pytest.mark.asyncio
async def test_two_stores_same_barcode_merge_into_one_card_two_price_rows(db_session, test_user):
    """Два файла (магазина) с одним штрихкодом → одна карточка, две строки
    цены — несмотря на РАЗНЫЕ названия/бренды/артикулы."""
    old_name = _uniq_name("Магазин1")
    new_name = _uniq_name("Магазин2СовсемДругоеНазвание")

    inn1 = "7701000101"
    contractor1_id = await find_or_create_contractor(
        db_session, "Штрихкод-Магазин1", inn1, match_by_name=False,
    )
    product = Product(name=old_name, category="Прочее", price=Decimal("100"))
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    db_session.add(ProductBarcode(product_id=product.id, barcode=_VALID_EAN13, contractor_id=contractor1_id))
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("100"), source="import",
        contractor_id=contractor1_id, store_article="SHOP1-ART",
    ))
    await db_session.commit()

    inn2 = "7701000102"
    col_idx = {
        "name": 0, "price": 1, "seller_inn": 2, "store_article": 3, "barcodes": 4,
    }
    data_rows = [(new_name, "150", inn2, "SHOP2-ART", [_VALID_EAN13])]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="barcode_merge.xlsx", current_user=test_user,
    )
    assert result["created"] == 0, result
    assert result["updated"] == 1, result
    assert result["barcodes_accepted"] == 1
    assert result["barcodes_rejected"] == 0
    assert await _count_by_name(db_session, new_name) == 0, "второй магазин не создаёт отдельную карточку"

    await db_session.refresh(product)
    assert product.name == old_name, "название существующей карточки не переписывается"

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 2, "вторая строка истории (магазин 2) должна появиться у ТОЙ ЖЕ карточки"
    assert "сведено" in result["rows"][0]["reason"] and "по штрихкоду" in result["rows"][0]["reason"]

    barcodes = (await db_session.execute(
        select(ProductBarcode).where(ProductBarcode.product_id == product.id)
    )).scalars().all()
    assert len(barcodes) == 1, "тот же штрихкод у того же товара — без дублей"


@pytest.mark.asyncio
async def test_upc12_and_ean13_form_match_same_card():
    """UPC-12 и соответствующий ему EAN-13 (с ведущим нулём) должны давать
    ОДИН ключ нормализации — проверяется на уровне normalize_barcode
    (products_import_match_barcode зависит от уже нормализованных значений,
    см. test_barcodes.py::test_upc12_and_its_ean13_form_give_same_key)."""
    from app.services.barcodes import normalize_barcode
    upc = "036000291452"
    assert normalize_barcode(upc) == normalize_barcode("0" + upc)


@pytest.mark.asyncio
async def test_invalid_checksum_barcode_rejected_and_does_not_merge(db_session, test_user):
    """Невалидная контрольная цифра — штрихкод отброшен, НЕ участвует в
    сведении (строка создаёт новый товар, как если бы штрихкода не было)."""
    existing_name = _uniq_name("СуществующийДляНеверного")
    new_name = _uniq_name("НовыйСНеверным")

    product = Product(name=existing_name, category="Прочее", price=Decimal("50"))
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    # Испорченная контрольная цифра валидного кода.
    bad_barcode = _VALID_EAN13[:-1] + str((int(_VALID_EAN13[-1]) + 1) % 10)
    db_session.add(ProductBarcode(product_id=product.id, barcode=_VALID_EAN13))
    await db_session.commit()

    col_idx = {"name": 0, "price": 1, "barcodes": 2}
    data_rows = [(new_name, "60", [bad_barcode])]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="barcode_invalid.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, result
    assert result["barcodes_accepted"] == 0
    assert result["barcodes_rejected"] == 1
    assert await _count_by_name(db_session, new_name) == 1


@pytest.mark.asyncio
async def test_same_store_different_store_article_same_barcode_not_merged(db_session, test_user):
    """Правило «один магазин не продаёт товар дважды» действует и для
    штрихкода: кандидат уже имеет строку истории ЭТОГО ЖЕ магазина с ДРУГИМ
    store_article — критерий (0.25) не сводит их, строка создаёт новый
    товар (или падает на другие критерии/создание — в этом тесте бренд/
    артикул не заданы, значит будет создан новый товар)."""
    existing_name = _uniq_name("ОдинМагазинШтрихкодСтарый")
    new_name = _uniq_name("ОдинМагазинШтрихкодНовый")

    inn = "7701000103"
    contractor_id = await find_or_create_contractor(
        db_session, "Штрихкод-один-магазин-дважды", inn, match_by_name=False,
    )
    product = Product(name=existing_name, category="Прочее", price=Decimal("200"))
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    db_session.add(ProductBarcode(product_id=product.id, barcode=_VALID_EAN13, contractor_id=contractor_id))
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("200"), source="import",
        contractor_id=contractor_id, store_article="OLD-ART-BC",
    ))
    await db_session.commit()

    col_idx = {
        "name": 0, "price": 1, "seller_inn": 2, "store_article": 3, "barcodes": 4,
    }
    # Тот же магазин (inn), тот же штрихкод, но ДРУГОЙ store_article.
    data_rows = [(new_name, "210", inn, "NEW-ART-BC", [_VALID_EAN13])]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="barcode_same_store.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, result
    assert await _count_by_name(db_session, new_name) == 1
    assert await _count_by_name(db_session, existing_name) == 1
