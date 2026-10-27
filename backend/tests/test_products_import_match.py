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
import random
import string
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


def _uniq_marker() -> str:
    """Уникальный маркер БЕЗ цифр (владелец, 27.10.2026, критерий (0.75)
    «название + индекс модели») — в отличие от _uniq_name (hex-суффикс
    почти всегда содержит цифры), этот маркер безопасно добавлять ОДИНАКОВО
    в оба названия теста без изменения набора цифро-буквенных токенов
    (ProductSignature.digit_tokens), который и есть ключ сравнения."""
    return "".join(random.choices(string.ascii_uppercase, k=8))


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
async def test_brand_article_match_merges_other_store_into_one_card(db_session, test_user):
    """Критерий (0.5) (РЕШЕНИЕ ВЛАДЕЛЬЦА, 27.10.2026): товар новой выгрузки,
    совпавший с уже имеющимся товаром ДРУГОГО магазина по бренду и артикулу
    производителя — сразу в ту же карточку (новая карточка не создаётся,
    цена второго магазина — отдельная строка истории)."""
    from app.models.product_price_history import ProductPriceHistory
    from app.services.contractor_resolve import find_or_create_contractor

    brand = "ЗУБР"
    article = "ЗДА-600"
    old_name = _uniq_name("БрендАртикулМагазин1")
    new_name = _uniq_name("БрендАртикулМагазин2")

    inn1 = "7701000011"
    contractor1_id = await find_or_create_contractor(
        db_session, "Магазин1 для теста brand_article", inn1, match_by_name=False,
    )
    product = Product(name=old_name, category="Прочее", price=Decimal("100"), manufacturer=brand, article=article)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("100"), source="import",
        contractor_id=contractor1_id, store_article="SA-M1-001",
    ))
    await db_session.commit()

    inn2 = "7701000022"
    col_idx = {
        "name": 0, "price": 1, "seller_inn": 2, "store_article": 3,
        "manufacturer": 4, "manufacturer_article": 5,
    }
    data_rows = [(new_name, "150", inn2, "SA-M2-777", brand, article)]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="brand_article_merge.xlsx", current_user=test_user,
    )
    assert result["created"] == 0, result
    assert result["updated"] == 1, result
    assert await _count_by_name(db_session, new_name) == 0, "второй магазин не должен создавать отдельную карточку"

    await db_session.refresh(product)
    assert product.name == old_name, "название существующей карточки не переписывается"

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 2, "вторая строка истории (магазин 2) должна появиться у ТОЙ ЖЕ карточки"
    assert "сведено" in result["rows"][0]["reason"] and "бренду и артикулу производителя" in result["rows"][0]["reason"]


@pytest.mark.asyncio
async def test_brand_article_same_store_different_store_article_not_merged(db_session, test_user):
    """Правило «один магазин не продаёт товар дважды»: кандидат уже имеет
    строку истории ЭТОГО ЖЕ магазина (contractor_id) с ДРУГИМ store_article —
    это разные товары, критерий (0.5) не сводит их."""
    from app.models.product_price_history import ProductPriceHistory
    from app.services.contractor_resolve import find_or_create_contractor

    brand = "ЗУБР"
    article = "ЗП-150"
    existing_name = _uniq_name("ОдинМагазинСтарый")
    new_name = _uniq_name("ОдинМагазинНовый")

    inn = "7701000033"
    contractor_id = await find_or_create_contractor(
        db_session, "Магазин для теста один-товар-дважды", inn, match_by_name=False,
    )
    product = Product(name=existing_name, category="Прочее", price=Decimal("200"), manufacturer=brand, article=article)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("200"), source="import",
        contractor_id=contractor_id, store_article="OLD-ART-1",
    ))
    await db_session.commit()

    col_idx = {
        "name": 0, "price": 1, "seller_inn": 2, "store_article": 3,
        "manufacturer": 4, "manufacturer_article": 5,
    }
    # Та же пара (бренд, артикул производителя), ТОТ ЖЕ магазин, но ДРУГОЙ
    # store_article — не тот же товар.
    data_rows = [(new_name, "210", inn, "NEW-ART-2", brand, article)]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="brand_article_same_store.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, result
    assert await _count_by_name(db_session, new_name) == 1, "тот же магазин под другим артикулом — отдельный товар"
    await db_session.refresh(product)
    assert product.price == Decimal("200"), "существующая карточка не должна была измениться"


@pytest.mark.asyncio
async def test_brand_article_bogus_manufacturer_never_merges(db_session, test_user):
    """manufacturer-«брак» (is_bogus_manufacturer решает ТОЛЬКО
    load_gala_catalog.item_to_row — здесь просто проверяем, что пустое
    manufacturer в строке не задействует критерий (0.5) вовсе)."""
    from app.services.contractor_resolve import find_or_create_contractor

    article = "ЛЕСТ-100"
    existing_name = _uniq_name("БракПроизводительСтарый")
    new_name = _uniq_name("БракПроизводительНовый")

    product = Product(name=existing_name, category="Прочее", price=Decimal("50"), manufacturer=None, article=article)
    db_session.add(product)
    await db_session.commit()

    inn = "7701000044"
    await find_or_create_contractor(db_session, "Магазин брак-производитель", inn, match_by_name=False)

    col_idx = {
        "name": 0, "price": 1, "seller_inn": 2, "store_article": 3,
        "manufacturer": 4, "manufacturer_article": 5,
    }
    # manufacturer пустой в строке (как после отбраковки load_gala_catalog.
    # item_to_row) — критерий (0.5) требует непустой manufacturer, не сработает.
    data_rows = [(new_name, "60", inn, "SA-BRAK-1", None, article)]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="brand_article_bogus.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, "без manufacturer критерий (0.5) не сводит — создан отдельный товар"
    assert await _count_by_name(db_session, new_name) == 1


@pytest.mark.asyncio
async def test_brand_article_different_brands_same_code_not_merged(db_session, test_user):
    """CR2016 — типоразмер батарейки, одинаковый у разных производителей
    (Philips/Kodak) — РАЗНЫЕ бренды с одинаковым кодом не сводятся (критерий
    (0.5) требует совпадения И бренда, И кода вместе)."""
    from app.services.contractor_resolve import find_or_create_contractor

    code = "CR2016"
    philips_name = _uniq_name("PhilipsCR2016")
    kodak_name = _uniq_name("KodakCR2016")

    product = Product(name=philips_name, category="Прочее", price=Decimal("30"), manufacturer="Philips", article=code)
    db_session.add(product)
    await db_session.commit()

    inn = "7701000055"
    await find_or_create_contractor(db_session, "Магазин для теста CR2016", inn, match_by_name=False)

    col_idx = {
        "name": 0, "price": 1, "seller_inn": 2, "store_article": 3,
        "manufacturer": 4, "manufacturer_article": 5,
    }
    data_rows = [(kodak_name, "35", inn, "SA-KODAK-1", "Kodak", code)]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="brand_article_cr2016.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, "разные бренды с одним кодом — разные товары"
    assert await _count_by_name(db_session, kodak_name) == 1
    assert await _count_by_name(db_session, philips_name) == 1


@pytest.mark.asyncio
async def test_brand_article_pending_store_split_not_merged(db_session, test_user):
    """Гард (владелец, 27.10.2026, риск Сима-ленда/Бауцентра): карточка, чей
    price_source_contractor — Сима-ленд (article_is_manufacturer=False, см.
    app.services.catalog_gala.stores.STORES), и у неё Product.article =
    НОМЕР МАГАЗИНА (старая трактовка, перенос split_store_articles.py --apply
    для неё ещё НЕ сделан — нет строки истории с заполненным store_article)
    — критерий (0.5) не должен сводить с ней товар другого магазина по
    случайному совпадению бренда + "артикля"-номера магазина."""
    from app.models.product_price_history import ProductPriceHistory
    from app.services.contractor_resolve import find_or_create_contractor

    brand = "Ярпожинвест"
    legacy_article = "4878510"  # на деле номер товара в Сима-ленде, не артикул производителя
    old_name = _uniq_name("СимаЛендНеПеренесён")
    new_name = _uniq_name("ДругойМагазинЯрпож")

    sima_contractor_id = await find_or_create_contractor(
        db_session, "ООО ТД «Сима-ленд»", "6679104850", match_by_name=False,
    )
    product = Product(
        name=old_name, category="Прочее", price=Decimal("100"),
        manufacturer=brand, article=legacy_article,
        price_source_contractor_id=sima_contractor_id,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    # Строка истории ЭТОГО магазина с ПУСТЫМ store_article — перенос ещё не
    # выполнен (ровно то, что split_store_articles.py --apply перенесёт
    # следующим прогоном).
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("100"), source="import",
        contractor_id=sima_contractor_id, store_article=None,
    ))
    await db_session.commit()

    inn2 = "7701000066"
    await find_or_create_contractor(db_session, "Другой магазин для теста split-гарда", inn2, match_by_name=False)

    col_idx = {
        "name": 0, "price": 1, "seller_inn": 2, "store_article": 3,
        "manufacturer": 4, "manufacturer_article": 5,
    }
    data_rows = [(new_name, "110", inn2, "SA-OTHER-1", brand, legacy_article)]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="brand_article_pending_split.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, "карточка, ждущая переноса артикула, не должна сводиться по номеру магазина"
    assert await _count_by_name(db_session, new_name) == 1
    await db_session.refresh(product)
    assert product.price == Decimal("100"), "существующая карточка Сима-ленда не должна была измениться"


@pytest.mark.asyncio
async def test_brand_article_after_split_still_not_merged_by_legacy_article(db_session, test_user):
    """После переноса (split_store_articles.py --apply): Product.article =
    NULL, store_article перенесён в историю — товар и так не попадёт в
    SQL-предвыборку load_candidates_by_brand_article (требует article IS NOT
    NULL), гард не нужен, но поведение должно оставаться «не сводится»."""
    from app.models.product_price_history import ProductPriceHistory
    from app.services.contractor_resolve import find_or_create_contractor

    brand = "Ярпожинвест"
    legacy_article = "4878510"
    old_name = _uniq_name("СимаЛендПеренесён")
    new_name = _uniq_name("ДругойМагазинПослеПереноса")

    sima_contractor_id = await find_or_create_contractor(
        db_session, "ООО ТД «Сима-ленд» переноc", "6679104850", match_by_name=False,
    )
    product = Product(
        name=old_name, category="Прочее", price=Decimal("100"),
        manufacturer=brand, article=None,  # перенос уже выполнен
        price_source_contractor_id=sima_contractor_id,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("100"), source="import",
        contractor_id=sima_contractor_id, store_article=legacy_article,
    ))
    await db_session.commit()

    inn2 = "7701000077"
    await find_or_create_contractor(db_session, "Другой магазин после переноса", inn2, match_by_name=False)

    col_idx = {
        "name": 0, "price": 1, "seller_inn": 2, "store_article": 3,
        "manufacturer": 4, "manufacturer_article": 5,
    }
    data_rows = [(new_name, "120", inn2, "SA-OTHER-2", brand, legacy_article)]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="brand_article_after_split.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, "после переноса Product.article пуст — критерий (0.5) не находит кандидата вовсе"
    assert await _count_by_name(db_session, new_name) == 1


@pytest.mark.asyncio
async def test_brand_article_manufacturer_store_card_still_merges(db_session, test_user):
    """Контрольный пример: магазин-производитель (МПО Электромонтаж,
    article_is_manufacturer=True) — гард его не касается, критерий (0.5)
    продолжает сводить карточки как раньше."""
    from app.models.product_price_history import ProductPriceHistory
    from app.services.contractor_resolve import find_or_create_contractor

    brand = "DEKraft"
    article = "14054DEK"
    old_name = _uniq_name("МПОСтарый")
    new_name = _uniq_name("МПОНовый")

    mpo_contractor_id = await find_or_create_contractor(
        db_session, "ЗАО «МПО Электромонтаж»", "7719079370", match_by_name=False,
    )
    product = Product(
        name=old_name, category="Прочее", price=Decimal("500"),
        manufacturer=brand, article=article,
        price_source_contractor_id=mpo_contractor_id,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("500"), source="import",
        contractor_id=mpo_contractor_id, store_article="MPO-001",
    ))
    await db_session.commit()

    inn2 = "7701000088"
    await find_or_create_contractor(db_session, "Другой магазин для DEKraft", inn2, match_by_name=False)

    col_idx = {
        "name": 0, "price": 1, "seller_inn": 2, "store_article": 3,
        "manufacturer": 4, "manufacturer_article": 5,
    }
    data_rows = [(new_name, "520", inn2, "SA-OTHER-3", brand, article)]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="brand_article_mpo.xlsx", current_user=test_user,
    )
    assert result["created"] == 0, result
    assert result["updated"] == 1, result
    assert await _count_by_name(db_session, new_name) == 0, "магазин-производитель — гард не исключает, карточки сводятся"


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


@pytest.mark.asyncio
async def test_name_model_match_merges_other_store_into_one_card(db_session, test_user):
    """Критерий (0.75) (владелец, 27.10.2026, «название + индекс модели»,
    products_import_match_name_model.py/product_name_signature.py) — тот же
    товар у ДРУГОГО магазина, названный по-другому (доп. слова техописания),
    но с тем же брендом и тем же цифро-буквенным индексом модели, сводится в
    ОДНУ карточку (вторая строка истории цены — у той же карточки), без
    manufacturer_article (критерий (0.5) здесь неприменим)."""
    from app.models.product_price_history import ProductPriceHistory
    from app.services.contractor_resolve import find_or_create_contractor

    marker = _uniq_marker()
    old_name = f"Перфоратор MAKITA M8701B {marker}"
    new_name = f"Перфоратор 800 Вт 2,3 Дж SDS-Plus Makita M8701B {marker}"

    inn1 = "7702000011"
    contractor1_id = await find_or_create_contractor(
        db_session, "Магазин1 для теста name_model", inn1, match_by_name=False,
    )
    product = Product(name=old_name, category="Прочее", price=Decimal("1000"), manufacturer="MAKITA")
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("1000"), source="import",
        contractor_id=contractor1_id, store_article="NM-M1-001",
    ))
    await db_session.commit()

    inn2 = "7702000022"
    col_idx = {"name": 0, "price": 1, "seller_inn": 2, "store_article": 3, "manufacturer": 4}
    data_rows = [(new_name, "1100", inn2, "NM-M2-777", "Makita")]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="name_model_merge.xlsx", current_user=test_user,
    )
    assert result["created"] == 0, result
    assert result["updated"] == 1, result
    assert await _count_by_name(db_session, new_name) == 0, "второй магазин не должен создавать отдельную карточку"

    await db_session.refresh(product)
    assert product.name == old_name

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 2, "вторая строка истории (магазин 2) должна появиться у ТОЙ ЖЕ карточки"
    assert "сведено" in result["rows"][0]["reason"] and "по названию и модели" in result["rows"][0]["reason"]


@pytest.mark.asyncio
async def test_name_model_different_product_type_same_code_not_merged(db_session, test_user):
    """«Шкаф для огнетушителя» ≠ «Пенал для огнетушителя» — тот же артикул
    производителя (82170) в названии, но разный вид товара (product_type) —
    product_name_signature.match() даёт decision="no", критерий (0.75) не
    сводит их, остаются ДВЕ разные карточки."""
    from app.services.contractor_resolve import find_or_create_contractor

    marker = _uniq_marker()
    cabinet_name = f"Шкаф для огнетушителя DAKEN Regon 82170 {marker}"
    case_name = f"Пенал для огнетушителя DAKEN Regon 82170 {marker}"

    product = Product(name=cabinet_name, category="Прочее", price=Decimal("2000"), manufacturer="DAKEN")
    db_session.add(product)
    await db_session.commit()

    inn = "7702000033"
    await find_or_create_contractor(db_session, "Магазин для теста Пенал/Шкаф", inn, match_by_name=False)

    col_idx = {"name": 0, "price": 1, "seller_inn": 2, "store_article": 3, "manufacturer": 4}
    data_rows = [(case_name, "500", inn, "NM-CASE-001", "DAKEN")]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="name_model_case_vs_cabinet.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, result
    assert await _count_by_name(db_session, cabinet_name) == 1
    assert await _count_by_name(db_session, case_name) == 1, "Пенал должен стать отдельной карточкой, не слиться со Шкафом"


@pytest.mark.asyncio
async def test_name_model_different_box_dimensions_not_merged(db_session, test_user):
    """Гофрокороб д600 vs д500 — разные размеры в самих цифро-буквенных
    токенах названия (жёсткий гейт digit_tokens, product_name_signature.py)
    — критерий (0.75) НЕ сводит, остаются две разные карточки."""
    from app.services.contractor_resolve import find_or_create_contractor

    marker = _uniq_marker()
    box600_name = f"Гофрокороб д600*ш400*в400 мм, марка Т24, профиль С, {marker}"
    box500_name = f"Гофрокороб д500*ш370*в120 мм, марка Т22, профиль С, {marker}"

    product = Product(name=box600_name, category="Прочее", price=Decimal("50"))
    db_session.add(product)
    await db_session.commit()

    inn = "7702000044"
    await find_or_create_contractor(db_session, "Магазин для теста гофрокороба", inn, match_by_name=False)

    col_idx = {"name": 0, "price": 1, "seller_inn": 2, "store_article": 3}
    data_rows = [(box500_name, "45", inn, "NM-BOX-001")]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="name_model_box_dims.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, result
    assert await _count_by_name(db_session, box600_name) == 1
    assert await _count_by_name(db_session, box500_name) == 1, "д500 должен стать отдельной карточкой, не слиться с д600"
