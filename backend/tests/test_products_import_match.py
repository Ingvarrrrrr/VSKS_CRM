"""Владелец, 2026-10-26 (план «каталог без дублей»): импорт каталога сравнивает
товары по названию и описанию без создания дублей — см. docstring
app/services/products_import_match.py и app/services/products_import_apply.py.
Покрывает: пустое описание в БД донаполняется; другое непустое описание не
создаёт дубль (оба режима replace_descriptions); повтор позиции внутри
ОДНОГО файла даёт 1 товар, а не 2 created; цена обновляется только если дата
строки не старше price_updated_at; категория «Не указано»/«Прочее»/пусто не
затирает существующую и не становится категорией нового товара (у нового —
DEFAULT_PRODUCT_CATEGORY).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.product import DEFAULT_PRODUCT_CATEGORY, Product
from app.models.product_description_history import ProductDescriptionHistory
from app.services.products_import_apply import apply_products_import

_UNIQ = "ТестМэтчИмпорт_20261026"


def _uniq_name(suffix: str) -> str:
    return f"{_UNIQ} {suffix} {uuid.uuid4().hex[:8]}"


async def _count_by_name(db_session, name: str) -> int:
    rows = (await db_session.execute(select(Product).where(Product.name == name))).scalars().all()
    return len(rows)


@pytest.mark.asyncio
async def test_empty_description_in_db_gets_filled_and_updated(db_session, test_user):
    name = _uniq_name("ПустоеОписание")
    product = Product(name=name, category="Прочее", description=None)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    col_idx = {"name": 0, "description": 1}
    data_rows = [(name, "Описание из файла")]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="match1.xlsx", current_user=test_user,
    )
    assert result["updated"] == 1
    assert result["created"] == 0

    await db_session.refresh(product)
    assert product.description == "Описание из файла"
    assert await _count_by_name(db_session, name) == 1


@pytest.mark.asyncio
async def test_different_nonempty_description_no_duplicate_default_mode(db_session, test_user):
    """replace_descriptions=False (дефолт) — описание в БД другое, НЕ
    трогаем, дубль не создаём."""
    name = _uniq_name("ДругоеОписаниеFalse")
    product = Product(name=name, category="Прочее", description="Старое описание из БД")
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    col_idx = {"name": 0, "description": 1}
    data_rows = [(name, "Новое описание из файла")]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="match2.xlsx", current_user=test_user,
    )
    assert result["created"] == 0
    assert await _count_by_name(db_session, name) == 1, "описание другое — дубль не должен создаваться"

    await db_session.refresh(product)
    assert product.description == "Старое описание из БД"
    row = result["rows"][0]
    assert row["action"] == "skipped"
    assert "описание в БД другое, оставлено" in row["reason"]


@pytest.mark.asyncio
async def test_different_nonempty_description_replaced_when_flag_true(db_session, test_user):
    """replace_descriptions=True — описание ЗАМЕНЯЕТСЯ файловым через
    set_product_description (история не теряется)."""
    # Финальное решение владельца (26.10.2026): replace_descriptions=True
    # заменяет описание файловым безусловно, даже если новый текст короче
    # старого — здесь новый текст длиннее, но это не требование.
    name = _uniq_name("ДругоеОписаниеTrue")
    product = Product(name=name, category="Прочее", description="Старое описание2")
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    col_idx = {"name": 0, "description": 1}
    data_rows = [(name, "Старое описание2, дополненное новым текстом")]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="match3.xlsx", current_user=test_user,
        replace_descriptions=True,
    )
    assert result["updated"] == 1
    assert await _count_by_name(db_session, name) == 1

    await db_session.refresh(product)
    assert product.description == "Старое описание2, дополненное новым текстом"

    hist = (await db_session.execute(
        select(ProductDescriptionHistory).where(ProductDescriptionHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 1
    assert hist[0].old_value == "Старое описание2"
    assert hist[0].new_value == "Старое описание2, дополненное новым текстом"


@pytest.mark.asyncio
async def test_duplicate_row_within_same_file_collapses_to_one_product(db_session, test_user):
    """Две одинаковые строки (новый товар, отсутствующий в БД) в ОДНОМ файле
    — итог 1 товар (created + updated), а не 2 created."""
    name = _uniq_name("ПовторВФайле")
    col_idx = {"name": 0, "description": 1, "price": 2}
    data_rows = [
        (name, "Описание повтора", "100"),
        (name, "Описание повтора", "100"),
    ]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="match4.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, result
    assert result["updated"] == 1, result
    assert await _count_by_name(db_session, name) == 1

    product = (await db_session.execute(select(Product).where(Product.name == name))).scalar_one()
    assert product.price == Decimal("100")


@pytest.mark.asyncio
async def test_price_older_date_not_applied_newer_date_applied(db_session, test_user):
    from datetime import datetime

    name = _uniq_name("ЦенаПоДате")
    # price_updated_at проставляем напрямую (не через actualize_product_price
    # — та пишет datetime.utcnow(), а тесту нужна КОНКРЕТНАЯ прошлая дата,
    # с которой сравнивается price_date_val строки импорта, Задача 5).
    product = Product(
        name=name, category="Прочее",
        price=Decimal("100"), price_source="manual",
        price_updated_at=datetime(2026, 1, 10),
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    col_idx = {"name": 0, "price": 1, "price_date": 2}

    # Строка со СТАРОЙ датой — цена не должна поменяться.
    result_old = await apply_products_import(
        db_session, [(name, "90", "05.01.2026")], col_idx,
        filename="match5_old.xlsx", current_user=test_user,
    )
    assert result_old["updated"] == 1
    await db_session.refresh(product)
    assert product.price == Decimal("100"), "цена со старой датой перетёрла актуальную"

    # Строка с НОВОЙ датой — цена должна поменяться.
    result_new = await apply_products_import(
        db_session, [(name, "120", "20.01.2026")], col_idx,
        filename="match5_new.xlsx", current_user=test_user,
    )
    assert result_new["updated"] == 1
    await db_session.refresh(product)
    assert product.price == Decimal("120"), "цена с более новой датой не применилась"


@pytest.mark.asyncio
async def test_category_not_overwritten_by_empty_like_values(db_session, test_user):
    name = _uniq_name("КатегорияНеЗатирается")
    product = Product(name=name, category="Мебель")
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    col_idx = {"name": 0, "category": 1}
    for empty_val in ("Не указано", "Прочее", ""):
        result = await apply_products_import(
            db_session, [(name, empty_val)], col_idx,
            filename="match6.xlsx", current_user=test_user,
        )
        assert result["updated"] == 1
        await db_session.refresh(product)
        assert product.category == "Мебель", f"категория затёрлась значением {empty_val!r}"


@pytest.mark.asyncio
async def test_store_article_match_updates_same_product_despite_renamed_title(db_session, test_user):
    """Критерий (0) (владелец, 27.10.2026): вторая загрузка того же магазина
    (contractor_id+store_article совпадают с уже существующей строкой
    истории цены) обновляет ТОТ ЖЕ товар, даже если название в файле
    изменилось — не создаёт дубль по новому названию."""
    from app.models.product_price_history import ProductPriceHistory
    from app.services.contractor_resolve import find_or_create_contractor

    inn = "7799887766"
    store_article = "SA-99001"
    old_name = _uniq_name("СтароеНазвание")
    new_name = _uniq_name("НовоеНазвание")

    contractor_id = await find_or_create_contractor(
        db_session, "Магазин для теста store_article", inn, match_by_name=False,
    )
    product = Product(name=old_name, category="Прочее", price=Decimal("100"))
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("100"), source="import",
        contractor_id=contractor_id, store_article=store_article,
    ))
    await db_session.commit()

    col_idx = {"name": 0, "price": 1, "seller_inn": 2, "store_article": 3}
    data_rows = [(new_name, "150", inn, store_article)]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="store_article_rename.xlsx", current_user=test_user,
    )
    assert result["created"] == 0, result
    assert result["updated"] == 1, result
    assert await _count_by_name(db_session, new_name) == 0, "по новому названию не создан отдельный товар"

    await db_session.refresh(product)
    assert product.name == old_name, "название товара не меняется этим механизмом"
    assert product.price == Decimal("150")


@pytest.mark.asyncio
async def test_new_product_without_category_gets_default(db_session, test_user):
    name = _uniq_name("НоваяКатегорияДефолт")
    col_idx = {"name": 0, "category": 1}
    result = await apply_products_import(
        db_session, [(name, "Не указано")], col_idx,
        filename="match7.xlsx", current_user=test_user,
    )
    assert result["created"] == 1
    product = (await db_session.execute(select(Product).where(Product.name == name))).scalar_one()
    assert product.category == DEFAULT_PRODUCT_CATEGORY
