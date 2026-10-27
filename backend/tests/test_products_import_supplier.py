"""Тесты режима supplier_description у apply_products_import (Задача 3,
владелец, 2026-10-26, загрузчик каталогов поставщиков GALA,
scripts/load_gala_catalog.py). Описание строки собирается из характеристик
через build_tech_description (ЕДИНСТВЕННАЯ сборка, ПРАВИЛО №6) и ведёт себя
как replace_descriptions=True; characteristics заменяются файловыми у
существующего товара, manufacturer/article заполняются только если пусты;
новый товар получает все три поля."""
import uuid

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.product_description_history import ProductDescriptionHistory
from app.services.products_import_apply import apply_products_import

_UNIQ = "ТестПоставщикОписание_20261026"


def _uniq_name(suffix: str) -> str:
    return f"{_UNIQ} {suffix} {uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_new_product_gets_characteristics_manufacturer_article_and_built_description(db_session, test_user):
    name = _uniq_name("Новый")
    chars = [{"name": "Серия", "value": "Mosaic", "unit": None}]
    col_idx = {"name": 0, "description": 1, "characteristics": 2, "manufacturer": 3, "manufacturer_article": 4}
    data_rows = [(name, "Накладка для розетки.", chars, "Legrand", "078604")]

    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="gala.json", current_user=test_user,
        supplier_description=True,
    )
    assert result["created"] == 1, result

    product = (await db_session.execute(select(Product).where(Product.name == name))).scalar_one()
    assert product.characteristics == chars
    assert product.manufacturer == "Legrand"
    assert product.article == "078604"
    assert product.description == "Накладка для розетки.\n\nСерия: Mosaic"


@pytest.mark.asyncio
async def test_existing_product_characteristics_replaced_manufacturer_article_filled_only_if_empty(db_session, test_user):
    # Описание старого товара намеренно похоже на новое (не обязательно по
    # финальному решению владельца 26.10.2026 — supplier_description теперь
    # заменяет описание файловым безусловно — но так тест нагляднее проверяет
    # именно характеристики/manufacturer/article, а не замену текста).
    name = _uniq_name("Существующий")
    product = Product(
        name=name, category="Прочее",
        description="Текст поставщика",
        characteristics=[{"name": "Старая", "value": "1", "unit": None}],
        manufacturer="Старый производитель",
        article=None,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    new_chars = [{"name": "Серия", "value": "Mosaic", "unit": None}]
    col_idx = {"name": 0, "description": 1, "characteristics": 2, "manufacturer": 3, "manufacturer_article": 4}
    data_rows = [(name, "Текст поставщика.", new_chars, "Legrand", "078604")]

    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="gala.json", current_user=test_user,
        supplier_description=True,
    )
    assert result["updated"] == 1, result

    await db_session.refresh(product)
    assert product.characteristics == new_chars, "characteristics заменяются файловыми"
    assert product.manufacturer == "Старый производитель", "manufacturer не пуст — не трогаем"
    assert product.article == "078604", "article был пуст — заполняем"
    assert product.description == "Текст поставщика.\n\nСерия: Mosaic"

    hist = (await db_session.execute(
        select(ProductDescriptionHistory).where(ProductDescriptionHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 1
    assert hist[0].old_value == "Текст поставщика"


@pytest.mark.asyncio
async def test_existing_product_empty_characteristics_in_file_not_erased(db_session, test_user):
    name = _uniq_name("ПустыеХарактеристики")
    old_chars = [{"name": "Старая", "value": "1", "unit": None}]
    product = Product(name=name, category="Прочее", characteristics=old_chars)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    col_idx = {"name": 0, "description": 1, "characteristics": 2}
    data_rows = [(name, None, [])]

    await apply_products_import(
        db_session, data_rows, col_idx,
        filename="gala.json", current_user=test_user,
        supplier_description=True,
    )
    await db_session.refresh(product)
    assert product.characteristics == old_chars, "пустой characteristics из файла не должен затирать существующий"


@pytest.mark.asyncio
async def test_duplicate_row_within_file_new_product_description_replaced_without_crash(db_session, test_user):
    """Повтор позиции внутри ОДНОГО файла, где второе вхождение несёт другое
    описание — товар ещё не flush'нут (product.id=None), set_product_description
    писала бы историю с product_id=None (NOT NULL violation, нашли на
    electro_mpo_breakers_all.json). Теперь для ещё не сохранённого товара
    описание просто присваивается без истории."""
    name = _uniq_name("ПовторВФайлеОписание")
    chars1 = [{"name": "Серия", "value": "A"}]
    chars2 = [{"name": "Серия", "value": "B"}]
    col_idx = {"name": 0, "description": 1, "characteristics": 2}
    data_rows = [
        (name, None, chars1),
        (name, None, chars2),
    ]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="gala_dup.json", current_user=test_user,
        supplier_description=True,
    )
    assert result["created"] == 1, result
    assert result["updated"] == 1, result
    assert not result["errors"], result["errors"]

    product = (await db_session.execute(select(Product).where(Product.name == name))).scalar_one()
    assert product.description == "Серия: B"
    assert product.characteristics == chars2

    hist = (await db_session.execute(
        select(ProductDescriptionHistory).where(ProductDescriptionHistory.product_id == product.id)
    )).scalars().all()
    assert hist == [], "у ещё не сохранённого товара истории не пишем"


@pytest.mark.asyncio
async def test_without_supplier_description_flag_fields_not_touched(db_session, test_user):
    """Без supplier_description=True col_idx["characteristics"] и пр. не
    читаются — поведение прежнее (описание строки не пересобирается)."""
    name = _uniq_name("БезФлага")
    col_idx = {"name": 0, "description": 1, "characteristics": 2, "manufacturer": 3, "article": 4}
    data_rows = [(name, "Простое описание", [{"name": "X", "value": "1"}], "Производитель", "Артикул")]

    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="plain.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, result
    product = (await db_session.execute(select(Product).where(Product.name == name))).scalar_one()
    assert product.description == "Простое описание"
    assert product.characteristics is None
    assert product.manufacturer is None
    assert product.article is None
