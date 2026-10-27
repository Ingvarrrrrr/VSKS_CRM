"""Категория/вид каталога для плановых позиций ФЭО по точному совпадению имени
(задача владельца, 27.10.2026) — см. докстринг app/services/feo_plan_catalog_category.py.

Часть 1: helper catalog_categories_by_normalized_name/catalog_category_for_name
изолированно (без эндпоинта). Часть 2: GET /feo-planned-items/comparison
действительно отдаёт catalog_category/catalog_product_type на каждой плановой
позиции (единственный эндпоинт, который их считает — остальные оставляют None).

Уникальный префикс на файл — исключает коллизию с реальными товарами на
локальной dev-БД (стенд — копия боевой базы), как и у test_product_catalog_homoglyph_fold.py.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.permission import RolePermission
from app.models.product import Product
from app.models.subsidy import Subsidy
from app.services.feo_plan_catalog_category import (
    catalog_categories_by_normalized_name,
    catalog_category_for_name,
)

_UNIQ = f"ТестКаталогКатегорийПлана_{uuid.uuid4().hex[:8]}"


# ── Часть 1: helper изолированно ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_unambiguous_match_returns_category(db_session):
    name = f"{_UNIQ} Перчатки латексные"
    db_session.add(Product(name=name, category="Спецодежда", product_type="Перчатки", price=Decimal("10")))
    await db_session.commit()

    m = await catalog_categories_by_normalized_name(db_session, [name])
    assert catalog_category_for_name(name, m) == ("Спецодежда", "Перчатки")


@pytest.mark.asyncio
async def test_case_and_whitespace_insensitive(db_session):
    """lower+trim+схлопывание пробелов — НИКАКОГО fuzzy: регистр и лишние
    пробелы не мешают точному совпадению, но другое слово не совпадёт."""
    db_name = f"{_UNIQ} Молоток  слесарный"  # двойной пробел внутри
    # _UNIQ сам не кейсится (его латинские hex-буквы участвуют в гомоглиф-свёртке
    # normalize_product_name по-разному в зависимости от регистра — не предмет
    # этого теста), регистр меняется только у чисто кириллических слов без цифр.
    query = f"  {_UNIQ} МОЛОТОК СЛЕСАРНЫЙ  "
    db_session.add(Product(name=db_name, category="Инструмент", product_type="Молотки", price=Decimal("5")))
    await db_session.commit()

    m = await catalog_categories_by_normalized_name(db_session, [query])
    assert catalog_category_for_name(query, m) == ("Инструмент", "Молотки")


@pytest.mark.asyncio
async def test_ambiguous_category_returns_none(db_session):
    """Два товара с одинаковым нормализованным именем, но РАЗНЫМИ категориями —
    результат None (не угадываем), ровно случай владельца «8 из 249»."""
    name = f"{_UNIQ} Футболка хлопок"
    db_session.add_all([
        Product(name=name, category="Одежда", product_type="Футболки", price=Decimal("3")),
        Product(name=name, category="Текстиль", product_type="Футболки", price=Decimal("4")),
    ])
    await db_session.commit()

    m = await catalog_categories_by_normalized_name(db_session, [name])
    category, product_type = catalog_category_for_name(name, m)
    assert category is None, "категория разошлась — должно быть None, а не угаданное значение"
    assert product_type == "Футболки", "вид совпал у обоих товаров — должен вернуться"


@pytest.mark.asyncio
async def test_no_match_returns_none(db_session):
    name = f"{_UNIQ} Товар, которого нет в каталоге вовсе"
    m = await catalog_categories_by_normalized_name(db_session, [name])
    assert catalog_category_for_name(name, m) == (None, None)


def test_empty_name_returns_none_without_query():
    """Пустое/None имя — None без обращения к карте (нормализация даёт '')."""
    assert catalog_category_for_name(None, {}) == (None, None)
    assert catalog_category_for_name("   ", {}) == (None, None)


@pytest.mark.asyncio
async def test_batch_is_single_query_for_several_names(db_session):
    """Один вызов на НЕСКОЛЬКО разных плановых позиций — без N+1: обе находятся
    в одной и той же построенной карте."""
    name_a = f"{_UNIQ} Каска защитная"
    name_b = f"{_UNIQ} Жилет сигнальный"
    db_session.add_all([
        Product(name=name_a, category="СИЗ", product_type="Каски", price=Decimal("7")),
        Product(name=name_b, category="СИЗ", product_type="Жилеты", price=Decimal("2")),
    ])
    await db_session.commit()

    m = await catalog_categories_by_normalized_name(db_session, [name_a, name_b, "не найдётся вовсе"])
    assert catalog_category_for_name(name_a, m) == ("СИЗ", "Каски")
    assert catalog_category_for_name(name_b, m) == ("СИЗ", "Жилеты")
    assert catalog_category_for_name("не найдётся вовсе", m) == (None, None)


# ── Часть 2: поле на эндпоинте GET /feo-planned-items/comparison ────────────

@pytest.fixture
async def subsidy_with_catalog_matched_plan(db_session, test_org):
    subsidy = Subsidy(name=f"CatCategory-{uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=3, name="Направление")
    db_session.add(cat)
    await db_session.flush()

    matched_name = f"{_UNIQ} Перчатки х/б"
    ambiguous_name = f"{_UNIQ} Канцтовары в ассортименте"
    unmatched_name = f"{_UNIQ} Позиция без товара в каталоге вовсе"

    db_session.add(Product(name=matched_name, category="Спецодежда", product_type="Перчатки", price=Decimal("10")))
    db_session.add_all([
        Product(name=ambiguous_name, category="Офис", product_type="Бумага", price=Decimal("1")),
        Product(name=ambiguous_name, category="Хозтовары", product_type="Бумага", price=Decimal("2")),
    ])

    item_matched = FeoPlannedItem(feo_category_id=cat.id, name=matched_name, amount=1000, is_active=True)
    item_ambiguous = FeoPlannedItem(feo_category_id=cat.id, name=ambiguous_name, amount=500, is_active=True)
    item_unmatched = FeoPlannedItem(feo_category_id=cat.id, name=unmatched_name, amount=200, is_active=True)
    db_session.add_all([item_matched, item_ambiguous, item_unmatched])
    await db_session.commit()
    return subsidy, cat, item_matched, item_ambiguous, item_unmatched


async def test_comparison_endpoint_returns_catalog_category_fields(
    client, auth_headers, test_user, db_session, subsidy_with_catalog_matched_plan,
):
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()
    subsidy, cat, item_matched, item_ambiguous, item_unmatched = subsidy_with_catalog_matched_plan

    resp = await client.get(
        f"/api/feo-planned-items/comparison?feo_category_id={cat.id}&subsidy_id={subsidy.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    planned = {row["id"]: row for row in resp.json()["planned"]}

    assert planned[item_matched.id]["catalog_category"] == "Спецодежда"
    assert planned[item_matched.id]["catalog_product_type"] == "Перчатки"

    assert planned[item_ambiguous.id]["catalog_category"] is None, \
        "разные категории у одноимённых товаров — не угадываем"
    assert planned[item_ambiguous.id]["catalog_product_type"] == "Бумага"

    assert planned[item_unmatched.id]["catalog_category"] is None
    assert planned[item_unmatched.id]["catalog_product_type"] is None
