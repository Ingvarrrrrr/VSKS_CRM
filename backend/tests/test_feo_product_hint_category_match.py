"""Владелец, 2026-09-16, п.F: GET /feo-planned-items/product-hint — совпадение
названия категории закупки товара (новый справочник) с названием узла ФЭО
поднимает кандидата (category_match=true); категория товара (Product.category)
участвует в том же сравнении, как и раньше. Без feo_category_id в запросе
category_match отсутствует (None) — прежнее поведение эндпоинта не меняется.
"""
from decimal import Decimal

import pytest

from app.models.feo_category import FeoCategory
from app.models.product import Product
from app.models.purchase_category import PurchaseCategory
from app.models.subsidy import Subsidy
from app.routers.feo_planned_items_matching import get_product_hint


async def _make_feo_category(db_session, name: str) -> FeoCategory:
    subsidy = Subsidy(name=f"Test subsidy for {name}", year=2026, budget=0)
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=3, name=name)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


@pytest.mark.asyncio
async def test_no_feo_category_id_omits_category_match(db_session, test_user):
    product = Product(name="Товар без контекста ФЭО", category="Прочее", price=Decimal("10"))
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    result = await get_product_hint(product_id=product.id, feo_category_id=None, db=db_session, _=test_user)
    assert result["category_match"] is None


@pytest.mark.asyncio
async def test_purchase_category_name_matches_feo_node_name(db_session, test_user):
    feo_cat = await _make_feo_category(db_session, "Пожарное оборудование")
    purchase_cat = PurchaseCategory(name="Пожарное оборудование")
    db_session.add(purchase_cat)
    await db_session.commit()
    await db_session.refresh(purchase_cat)

    product = Product(name="Краги пожарного", category="СИЗ", price=Decimal("10"))
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    product.purchase_categories = [purchase_cat]
    await db_session.commit()

    result = await get_product_hint(
        product_id=product.id, feo_category_id=feo_cat.id, db=db_session, _=test_user,
    )
    assert result["category_match"] is True


@pytest.mark.asyncio
async def test_product_category_alone_still_matches(db_session, test_user):
    """Категория товара (без категорий закупки вообще) — как раньше, тоже
    участвует в сравнении."""
    feo_cat = await _make_feo_category(db_session, "СИЗ")
    product = Product(name="Перчатки", category="СИЗ", price=Decimal("5"))
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    result = await get_product_hint(
        product_id=product.id, feo_category_id=feo_cat.id, db=db_session, _=test_user,
    )
    assert result["category_match"] is True


@pytest.mark.asyncio
async def test_no_overlap_is_false(db_session, test_user):
    feo_cat = await _make_feo_category(db_session, "Канцелярские товары")
    product = Product(name="Ноутбук", category="Оргтехника", price=Decimal("50000"))
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    result = await get_product_hint(
        product_id=product.id, feo_category_id=feo_cat.id, db=db_session, _=test_user,
    )
    assert result["category_match"] is False
