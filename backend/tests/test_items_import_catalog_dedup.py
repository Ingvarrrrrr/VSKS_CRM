"""Дедуп каталога товаров при импорте позиций закупки (владелец, 2026-09-14):

Причина прежних дублей: точное совпадение названия сравнивалось только по
обрезанным по краям пробелам + lower() — без схлопывания повторяющихся
пробелов ВНУТРИ строки, так что «Бензорез Champion  3.5 кВт» (двойной пробел)
и «Бензорез Champion 3.5 кВт» заводили ДВА товара. По базе набралось 41
группа дублей (82 товара) — часть с заполненным описанием (из ТЗ), часть без.

Требования владельца, дословно: «При точном совпадении названия загрузка
ДОПОЛНЯЕТ существующий товар, а не заводит новый. Плюс сопоставление
предпочитает запись с ТЗ. А ещё добавляет ещё одну запись по цене к уже
имеющимся, чтобы правильнее считалась средняя.»

Единая точка входа — app/services/product_catalog_match.py (normalize_product_name /
pick_preferred / index_products_by_name / find_exact_product) и
app/services/items_import_catalog.py (_upsert_product_to_catalog /
_apply_import_to_existing_product), см. их докстринги.

Гоняется ПО ОДНОМУ УЗЛУ за вызов pytest (флейк pytest-asyncio «different
loop» при параллельном запуске — см. project_pytest_asyncio_loop_flake в
памяти проекта). Тестовые данные живут внутри db_session/outer-transaction
(conftest.py) и откатываются автоматически — ничего не остаётся в БД.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.items_import_catalog import _upsert_product_to_catalog
from app.services.product_catalog_match import (
    find_exact_product,
    index_products_by_name,
    normalize_product_name,
)

# Уникальный префикс на файл — исключает коллизию с реальными товарами на
# локальной dev-БД (см. project_prod_purchases_backup_20260905 и т.п. — стенд
# это КОПИЯ боевой базы).
_UNIQ = "ТестДедупКаталога_20260914"


@pytest.mark.asyncio
async def test_exact_match_does_not_create_second_product(db_session):
    """Загрузка строки с именем существующего товара — в т.ч. с двойным
    пробелом внутри имени, как в реальном инциденте — НЕ заводит второй
    товар, а находит существующий."""
    name_in_db = f"{_UNIQ} A  Бензорез"  # двойной пробел внутри
    name_in_file = f"{_UNIQ} A Бензорез"  # одинарный — тот же товар после нормализации
    p = Product(name=name_in_db, category="Прочее", price=Decimal("100"))
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    pid = await _upsert_product_to_catalog(db_session, name_in_file, "товар", Decimal("150"))
    assert pid == p.id

    rows = (await db_session.execute(
        select(Product).where(Product.name.in_([name_in_db, name_in_file]))
    )).scalars().all()
    assert len(rows) == 1, "загрузка завела второй товар вместо того, чтобы найти существующий"


@pytest.mark.asyncio
async def test_empty_field_filled_nonempty_not_overwritten(db_session):
    """Пустое поле (описание) существующего товара дозаполняется из файла;
    уже заполненное (категория) не затирается."""
    p = Product(name=f"{_UNIQ} B", category="Электроника", description="", price=Decimal("0"))
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    await _upsert_product_to_catalog(
        db_session, f"{_UNIQ} B", "товар", None,
        description="Описание из файла",
        category="Прочее",  # НЕ должно перетереть уже заполненную "Электроника"
    )
    await db_session.refresh(p)
    assert p.description == "Описание из файла"
    assert p.category == "Электроника"


@pytest.mark.asyncio
async def test_price_added_to_history_not_overwritten_silently(db_session):
    """Совпадение по имени + цена из файла → НОВАЯ запись в
    product_price_history (не молча перезаписанная текущая цена) — через
    единую точку app.services.price_actualization.actualize_product_price."""
    p = Product(name=f"{_UNIQ} C", category="Прочее", price=Decimal("100"))
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    await _upsert_product_to_catalog(db_session, f"{_UNIQ} C", "товар", Decimal("222"))
    await db_session.refresh(p)
    assert p.price == Decimal("222")

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == p.id)
    )).scalars().all()
    assert len(hist) == 1
    assert hist[0].price == Decimal("222")
    assert hist[0].source == "import"


@pytest.mark.asyncio
async def test_matching_prefers_product_with_description_among_duplicates(db_session):
    """Два одноимённых товара в каталоге (дубль, ещё не слитый) — подбор по
    точному имени берёт того, у кого заполнено описание («сопоставление
    предпочитает запись с ТЗ», владелец 2026-09-14)."""
    p_blank = Product(name=f"{_UNIQ} D", category="Прочее", description="", price=Decimal("10"))
    p_desc = Product(name=f"{_UNIQ} D", category="Прочее", description="Полное ТЗ из файла", price=Decimal("20"))
    db_session.add_all([p_blank, p_desc])
    await db_session.commit()
    await db_session.refresh(p_blank)
    await db_session.refresh(p_desc)

    found = await find_exact_product(db_session, f"{_UNIQ} D")
    assert found is not None
    assert found.id == p_desc.id, "подбор должен был предпочесть запись с заполненным описанием"

    indexed = index_products_by_name([p_blank, p_desc])
    assert indexed[normalize_product_name(f"{_UNIQ} D")].id == p_desc.id


@pytest.mark.asyncio
async def test_new_product_from_import_gets_price_updated_at_and_history_date(db_session):
    """Владелец, 2026-09-20: цена, пришедшая импортом ТЗ, у НОВОГО товара
    оставалась без даты («все цены старше 60 дней», «на основании 1 цены»,
    прочерки в колонке «Дата») — Product(price=...) создавался напрямую, в
    обход actualize_product_price. Теперь цена нового товара проходит через
    ту же единую точку (post-flush, т.к. ProductPriceHistory.product_id
    NOT NULL), что и для уже существующего — price_updated_at и
    product_price_history.collected_at обязаны быть заполнены."""
    pid = await _upsert_product_to_catalog(
        db_session, f"{_UNIQ} F Новый из импорта", "товар", Decimal("777"),
        import_note="Смарт-импорт из файла, тест, 20.09.2026 00:00",
    )
    p = (await db_session.execute(select(Product).where(Product.id == pid))).scalar_one()
    assert p.price == Decimal("777")
    assert p.price_updated_at is not None, "новый товар из импорта остался без даты актуализации цены"
    assert p.price_source == "import"

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == pid)
    )).scalars().all()
    assert len(hist) == 1
    assert hist[0].price == Decimal("777")
    assert hist[0].source == "import"
    assert hist[0].collected_at is not None, "строка истории цены нового товара осталась без даты"


@pytest.mark.asyncio
async def test_different_names_still_create_separate_products(db_session):
    """Товары с РАЗНЫМИ названиями по-прежнему создаются раздельно (никакого
    fuzzy-слияния разных товаров)."""
    pid1 = await _upsert_product_to_catalog(db_session, f"{_UNIQ} E1", "товар", Decimal("5"))
    pid2 = await _upsert_product_to_catalog(db_session, f"{_UNIQ} E2", "товар", Decimal("6"))
    assert pid1 != pid2

    rows = (await db_session.execute(
        select(Product).where(Product.name.in_([f"{_UNIQ} E1", f"{_UNIQ} E2"]))
    )).scalars().all()
    assert {r.id for r in rows} == {pid1, pid2}
