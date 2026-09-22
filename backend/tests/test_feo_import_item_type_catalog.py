"""Тип плановой позиции («товар/услуга/работа») из файла vs товар каталога
с ТЕМ ЖЕ именем — решение владельца, 22.09 (см. докстринг
app/services/feo_import_item_types.py):

  1. Колонка «Тип» пуста, в каталоге ОДИН товар с точно таким же (после
     нормализации) именем → item_type берётся из Product.item_kind,
     warning `item_type_from_catalog`.
  2. Колонка заполнена и совпадает с товаром каталога → без вопросов.
  3. Колонка заполнена и ОТЛИЧАЕТСЯ → конфликт: `item_type_conflicts` в
     ответе (и dry_run, и боевого импорта); решение — `item_type_decisions`
     ({row: "file"|"catalog"}), ОТДЕЛЬНЫЙ канал от `duplicate_resolutions`
     (Правило №6 — разная природа ключа, см. докстринг модуля). Без решения
     на боевом импорте — применяется тип из файла, каталог не трогается,
     warning `item_type_conflict_unresolved`; на dry_run — конфликт только
     показан, этого warning нет (ничего ещё не применено).
  4. Товара с таким именем нет (или их 2+ — неоднозначность, каталог не
     используется вовсе) → тип из колонки как есть.

Тот же приём вызова `_do_feo_import` напрямую списком строк и те же
`mk_row`/`_make_subsidy`/`_cleanup_subsidy`/`_get_categories`/`_get_items`/
`_IDX`, что и в test_feo_import_tree.py (Правило №6 — не дублировать макет
строки второй раз); `_import`-обёртка с `dry_run`/`item_type_decisions` — по
образцу test_feo_import_budget_conflicts.py::_import.

Гонять по одному узлу за вызов pytest в контейнере (флейк pytest-asyncio
«different loop» — project_pytest_asyncio_loop_flake, формально починен
15.09, но исторический стиль тестов ФЭО-импорта этого держится)."""
import json
import uuid

import pytest
from sqlalchemy import delete

from app.models.product import Product
from app.routers.feo_categories import _do_feo_import
from tests.test_feo_import_tree import (
    _IDX,
    _cleanup_subsidy,
    _get_categories,
    _get_items,
    _make_subsidy,
    mk_row,
)


async def _import(db_session, subsidy_id, rows, dry_run=False, item_type_decisions=None):
    return await _do_feo_import(
        rows=rows,
        c_subsidy=None,
        c_lvl2=_IDX["lvl2"], c_lvl3=_IDX["lvl3"], c_lvl4=_IDX["lvl4"], c_lvl5=_IDX["item_name"],
        c_qty=None, c_unit=None, c_item_amt=None,
        c_code=_IDX["code"], c_appendix=_IDX["appendix"], c_budget=_IDX["budget"], c_active=_IDX["active"],
        c_amt_lvl2=_IDX["amt_lvl2"],
        c_row_feo_qty=_IDX["feo_qty"], c_row_feo_unit=_IDX["feo_unit"],
        c_row_feo_price=_IDX["feo_price"], c_row_feo_sum=_IDX["feo_sum"],
        c_row_plan_qty=_IDX["plan_qty"], c_row_plan_unit=_IDX["plan_unit"],
        c_row_plan_price=_IDX["plan_price"], c_row_plan_sum=_IDX["plan_sum"],
        c_item_type=_IDX["item_type"],
        default_subsidy_id=subsidy_id,
        dry_run=dry_run,
        item_type_decisions=json.dumps(item_type_decisions) if item_type_decisions else "",
        db=db_session,
    )


async def _make_product(db_session, name: str, item_kind: str) -> Product:
    p = Product(name=name, category="Прочее", item_kind=item_kind)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _cleanup_products(db_session, product_ids: list) -> None:
    if not product_ids:
        return
    await db_session.execute(delete(Product).where(Product.id.in_(product_ids)))
    await db_session.commit()


def _row(item_name: str, item_type: str | None = None):
    return mk_row(
        lvl2="Направление", lvl3="Категория", item_name=item_name, item_type=item_type,
        plan_qty="1", plan_unit="шт", plan_price="1000", plan_sum="1000",
    )


# --- 1. Колонка пуста, каталог знает тип -> автозаполнение -----------------

@pytest.mark.asyncio
async def test_empty_column_gets_type_from_catalog(db_session):
    subsidy = await _make_subsidy(db_session)
    item_name = f"Автозаполнение из каталога {uuid.uuid4().hex[:8]}"
    product = await _make_product(db_session, item_name, "услуга")
    try:
        result = await _import(db_session, subsidy.id, [_row(item_name)])
        assert result["errors"] == []
        assert result["item_type_conflicts"] == []

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Категория")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        assert items[0].item_type == "услуга", "тип обязан подтянуться из каталога"

        catalog_warnings = [w for w in result["warnings"] if w["kind"] == "item_type_from_catalog"]
        assert len(catalog_warnings) == 1
        assert item_name in catalog_warnings[0]["message"]
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
        await _cleanup_products(db_session, [product.id])


# --- 2. Колонка совпадает с каталогом -> без вопросов -----------------------

@pytest.mark.asyncio
async def test_column_matches_catalog_no_conflict(db_session):
    subsidy = await _make_subsidy(db_session)
    item_name = f"Совпадение с каталогом {uuid.uuid4().hex[:8]}"
    product = await _make_product(db_session, item_name, "товар")
    try:
        result = await _import(db_session, subsidy.id, [_row(item_name, "Товар")])
        assert result["errors"] == []
        assert result["item_type_conflicts"] == []
        assert not any(
            w["kind"] in ("item_type_from_catalog", "item_type_conflict_unresolved")
            for w in result["warnings"]
        )

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Категория")
        items = await _get_items(db_session, leaf.id)
        assert items[0].item_type == "товар"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
        await _cleanup_products(db_session, [product.id])


# --- 3. Колонка отличается -> конфликт: dry_run показывает, боевой без
#        решения применяет тип из файла и НЕ трогает каталог ----------------

@pytest.mark.asyncio
async def test_conflict_dry_run_then_unresolved_real_import(db_session):
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    item_name = f"Конфликт типов {uuid.uuid4().hex[:8]}"
    product = await _make_product(db_session, item_name, "товар")
    # Капчу id ДО dry_run: `_import` откатывает транзакцию (db.rollback()),
    # что истекает (expire) все атрибуты уже загруженных ORM-объектов сессии
    # — необёрнутый повторный доступ к product.id после этого вне greenlet-
    # контекста падает MissingGreenlet, а не просто отдаёт старое значение.
    product_id = product.id
    try:
        rows = [_row(item_name, "Услуга")]

        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        assert preview["errors"] == []
        conflicts = preview["item_type_conflicts"]
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c["row"] == 2
        assert c["item_name"] == item_name
        assert c["file_type"] == "услуга"
        assert c["catalog_type"] == "товар"
        assert c["product_id"] == product_id
        assert c["product_name"] == item_name
        assert c["decision"] is None
        assert not any(w["kind"] == "item_type_conflict_unresolved" for w in preview["warnings"]), (
            "dry_run только показывает конфликт, ничего не применено"
        )

        result = await _import(db_session, subsidy_id, rows)
        assert result["errors"] == []
        assert result["item_type_conflicts"][0]["decision"] is None
        unresolved = [w for w in result["warnings"] if w["kind"] == "item_type_conflict_unresolved"]
        assert len(unresolved) == 1

        cats = await _get_categories(db_session, subsidy_id)
        leaf = next(c for c in cats if c.name == "Категория")
        items = await _get_items(db_session, leaf.id)
        assert items[0].item_type == "услуга", "без решения — побеждает тип из файла"

        await db_session.refresh(product)
        assert product.item_kind == "товар", "без явного решения каталог не трогаем"
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)
        await _cleanup_products(db_session, [product_id])


# --- 4. Решение 'file' -> тип из файла И перенесён в Product.item_kind ------

@pytest.mark.asyncio
async def test_conflict_resolution_file_updates_catalog(db_session):
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    item_name = f"Решение файл {uuid.uuid4().hex[:8]}"
    product = await _make_product(db_session, item_name, "товар")
    try:
        rows = [_row(item_name, "Работа")]
        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        row_num = preview["item_type_conflicts"][0]["row"]

        result = await _import(db_session, subsidy_id, rows, item_type_decisions={row_num: "file"})
        assert result["errors"] == []
        assert result["item_type_conflicts"][0]["decision"] == "file"
        assert not any(w["kind"] == "item_type_conflict_unresolved" for w in result["warnings"])

        cats = await _get_categories(db_session, subsidy_id)
        leaf = next(c for c in cats if c.name == "Категория")
        items = await _get_items(db_session, leaf.id)
        assert items[0].item_type == "работа"

        await db_session.refresh(product)
        assert product.item_kind == "работа", "решение 'file' обязано перенести тип в каталог"
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)
        await _cleanup_products(db_session, [product.id])


# --- 5. Решение 'catalog' -> тип каталога, товар не трогаем -----------------

@pytest.mark.asyncio
async def test_conflict_resolution_catalog_keeps_catalog_type(db_session):
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    item_name = f"Решение каталог {uuid.uuid4().hex[:8]}"
    product = await _make_product(db_session, item_name, "услуга")
    try:
        rows = [_row(item_name, "Товар")]
        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        row_num = preview["item_type_conflicts"][0]["row"]

        result = await _import(db_session, subsidy_id, rows, item_type_decisions={row_num: "catalog"})
        assert result["errors"] == []
        assert result["item_type_conflicts"][0]["decision"] == "catalog"

        cats = await _get_categories(db_session, subsidy_id)
        leaf = next(c for c in cats if c.name == "Категория")
        items = await _get_items(db_session, leaf.id)
        assert items[0].item_type == "услуга"

        await db_session.refresh(product)
        assert product.item_kind == "услуга", "решение 'catalog' товар не трогает"
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)
        await _cleanup_products(db_session, [product.id])


# --- 6. Товара в каталоге нет -> тип из колонки как есть, конфликта нет ----

@pytest.mark.asyncio
async def test_no_catalog_product_keeps_file_type(db_session):
    subsidy = await _make_subsidy(db_session)
    try:
        item_name = f"Товара в каталоге нет {uuid.uuid4().hex[:8]}"
        result = await _import(db_session, subsidy.id, [_row(item_name, "Работа")])
        assert result["errors"] == []
        assert result["item_type_conflicts"] == []
        assert not any(
            w["kind"] in ("item_type_from_catalog", "item_type_conflict_unresolved")
            for w in result["warnings"]
        )

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Категория")
        items = await _get_items(db_session, leaf.id)
        assert items[0].item_type == "работа"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 7. Неоднозначное имя (2 товара) -> каталог не используется ------------

@pytest.mark.asyncio
async def test_ambiguous_catalog_name_not_used(db_session):
    subsidy = await _make_subsidy(db_session)
    item_name = f"Дубликат товара ФЭО {uuid.uuid4().hex[:8]}"
    p1 = await _make_product(db_session, item_name, "товар")
    p2 = await _make_product(db_session, item_name, "услуга")
    try:
        result = await _import(db_session, subsidy.id, [_row(item_name)])
        assert result["errors"] == []
        assert result["item_type_conflicts"] == []
        assert not any(w["kind"] == "item_type_from_catalog" for w in result["warnings"])

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Категория")
        items = await _get_items(db_session, leaf.id)
        assert items[0].item_type is None, "неоднозначность — ни колонки, ни каталога, тип пуст"

        await db_session.refresh(p1)
        await db_session.refresh(p2)
        assert p1.item_kind == "товар", "ни один из дублей не тронут"
        assert p2.item_kind == "услуга"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
        await _cleanup_products(db_session, [p1.id, p2.id])
