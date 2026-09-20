"""Свёртка категории ФЭО в плановую позицию (владелец, 2026-09-20).

КОНТЕКСТ: старый фолбэк импорта ФЭО (services/feo_import_apply.py:1083-1119)
создавал КАТЕГОРИЮ и внутри неё ОДНУ плановую позицию того же имени вместо
того, чтобы завести позицию сразу в родительской категории — на бою 240
таких пар. GET /api/feo-categories/collapse-candidates находит кандидатов,
POST /api/feo-categories/{cat_id}/collapse-to-item сворачивает одну,
POST /api/feo-categories/collapse-bulk — пакетно, по одной в своей
транзакции.

Фикстуры — по образцу tests/test_feo_plan_tree_scenarios.py (реальная БД
через db_session/client, откатывается тестовой транзакцией). Права —
superadmin (бывает и require_tab('feo_categories'), и
_require_feo_category_write без похода в матрицу прав — не то, что здесь
проверяется).
"""
from decimal import Decimal

import pytest

from app.services.feo_plan import compute_feo_plan_tree


async def _make_subsidy(db_session, org_id, budget=1_000_000):
    from app.models.subsidy import Subsidy
    import uuid
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}", year=2026, budget=budget,
        org_id=org_id, require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, parent_id=None, **kwargs):
    from app.models.feo_category import FeoCategory
    import uuid
    level = 1 if parent_id is None else 2
    cat = FeoCategory(
        subsidy_id=subsidy_id, parent_id=parent_id, level=level,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"), **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, name, quantity, amount, **kwargs):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id, name=name,
        quantity=Decimal(str(quantity)), unit="шт", amount=Decimal(str(amount)),
        is_active=kwargs.pop("is_active", True), **kwargs,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _make_purchase_with_item(db_session, subsidy_id, feo_category_id, feo_planned_item_id=None, amount=1000):
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    total = Decimal(str(amount))
    p = Purchase(
        subsidy_id=subsidy_id, feo_category_id=feo_category_id, item_name="Тест-закупка",
        status="plan_schedule", planned_quantity=Decimal("1"),
        planned_total_price=total, total_nmck=total, nmck=total,
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id, item_name="Тест-позиция", quantity=Decimal("1"), unit="шт",
        unit_price=total, total_price=total, feo_category_id=feo_category_id,
        feo_planned_item_id=feo_planned_item_id, over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(pi)
    return p, pi


# ---------------------------------------------------------------------------
# 1) Деньги ФЭО категории переезжают на позицию; итог плана корня не меняется
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collapse_transfers_feo_money_and_preserves_root_plan(client, db_session, superadmin_headers, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    root = await _make_category(db_session, subsidy.id, name="Направление")
    dup_cat = await _make_category(
        db_session, subsidy.id, parent_id=root.id, name="Канцтовары",
        feo_quantity=Decimal("1"), feo_amount=Decimal("50000"), feo_unit="компл.",
    )
    item = await _make_planned_item(db_session, dup_cat.id, "Канцтовары", 1, 50000)

    tree_before = await compute_feo_plan_tree(db_session, [subsidy.id])
    assert tree_before[root.id]["plan"] == 50000.0
    assert tree_before[root.id]["display"] == 50000.0

    resp = await client.post(
        f"/api/feo-categories/{dup_cat.id}/collapse-to-item", headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["category_id"] == dup_cat.id
    assert body["planned_item_id"] == item.id
    assert body["parent_id"] == root.id

    from app.models.feo_category import FeoCategory
    from app.models.feo_planned_item import FeoPlannedItem
    from sqlalchemy import select

    assert (await db_session.execute(
        select(FeoCategory).where(FeoCategory.id == dup_cat.id)
    )).scalar_one_or_none() is None

    moved_item = (await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.id == item.id)
    )).scalar_one()
    assert moved_item.feo_category_id == root.id
    assert moved_item.feo_amount == Decimal("50000")
    assert moved_item.feo_quantity == Decimal("1")
    assert moved_item.is_feo_breakdown is True

    tree_after = await compute_feo_plan_tree(db_session, [subsidy.id])
    assert tree_after[root.id]["plan"] == 50000.0, "план корня обязан совпасть до/после свёртки"
    assert tree_after[root.id]["display"] == 50000.0


@pytest.mark.asyncio
async def test_collapse_conflicting_feo_money_returns_409(client, db_session, superadmin_headers, test_org):
    """У категории и у позиции ОБЕ заданы свои суммы ФЭО, и они не совпадают —
    перенос отменяется 409, ничего не меняется."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    root = await _make_category(db_session, subsidy.id, name="Направление")
    cat = await _make_category(
        db_session, subsidy.id, parent_id=root.id, name="Спорная",
        feo_quantity=Decimal("1"), feo_amount=Decimal("50000"),
    )
    item = await _make_planned_item(
        db_session, cat.id, "Спорная", 1, 50000, feo_amount=Decimal("99999"),
    )

    resp = await client.post(
        f"/api/feo-categories/{cat.id}/collapse-to-item", headers=superadmin_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "не совпадают" in resp.text

    from app.models.feo_category import FeoCategory
    from sqlalchemy import select
    assert (await db_session.execute(
        select(FeoCategory).where(FeoCategory.id == cat.id)
    )).scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# 2) Ссылки закупки/позиции закупки переезжают на родителя; feo_planned_item_id
#    сохраняется
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collapse_relinks_purchase_refs_keeps_planned_item_link(client, db_session, superadmin_headers, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    root = await _make_category(db_session, subsidy.id, name="Направление")
    cat = await _make_category(db_session, subsidy.id, parent_id=root.id, name="Оборудование")
    item = await _make_planned_item(db_session, cat.id, "Оборудование", 1, 1000)
    purchase, purchase_item = await _make_purchase_with_item(
        db_session, subsidy.id, cat.id, feo_planned_item_id=item.id, amount=1000,
    )

    resp = await client.post(
        f"/api/feo-categories/{cat.id}/collapse-to-item", headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["moved_refs"]["purchases"] == 1
    assert body["moved_refs"]["purchase_items"] == 1

    # Правки применены через Core bulk UPDATE в обход ORM identity map — уже
    # загруженные объекты purchase/purchase_item не обновляются автосном при
    # обычном select() (identity map отдаёт закэшированные атрибуты), нужен
    # явный refresh перед проверкой актуального состояния в БД.
    await db_session.refresh(purchase)
    await db_session.refresh(purchase_item)
    assert purchase.feo_category_id == root.id
    assert purchase_item.feo_category_id == root.id
    assert purchase_item.feo_planned_item_id == item.id, "ссылка на плановую позицию не должна теряться"


# ---------------------------------------------------------------------------
# 3) 409: подкатегории / две активные позиции / корневая категория
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collapse_blocked_by_subcategories(client, db_session, superadmin_headers, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    root = await _make_category(db_session, subsidy.id, name="Направление")
    mid = await _make_category(db_session, subsidy.id, parent_id=root.id, name="С подкатегориями")
    await _make_category(db_session, subsidy.id, parent_id=mid.id, name="Дочерняя")
    await _make_planned_item(db_session, mid.id, "С подкатегориями", 1, 500)

    resp = await client.post(
        f"/api/feo-categories/{mid.id}/collapse-to-item", headers=superadmin_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "подкатегории" in resp.text


@pytest.mark.asyncio
async def test_collapse_blocked_by_two_active_items(client, db_session, superadmin_headers, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    root = await _make_category(db_session, subsidy.id, name="Направление")
    cat = await _make_category(db_session, subsidy.id, parent_id=root.id, name="Две позиции")
    await _make_planned_item(db_session, cat.id, "Позиция 1", 1, 500)
    await _make_planned_item(db_session, cat.id, "Позиция 2", 1, 700)

    resp = await client.post(
        f"/api/feo-categories/{cat.id}/collapse-to-item", headers=superadmin_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "активных плановых позиций" in resp.text


@pytest.mark.asyncio
async def test_collapse_blocked_for_root_category(client, db_session, superadmin_headers, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    root = await _make_category(db_session, subsidy.id, name="Корневая")
    await _make_planned_item(db_session, root.id, "Корневая", 1, 500)

    resp = await client.post(
        f"/api/feo-categories/{root.id}/collapse-to-item", headers=superadmin_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "родительской категории" in resp.text


# ---------------------------------------------------------------------------
# 4) GET /collapse-candidates: дубль-имя найден, категория с двумя позициями
#    не отдаётся
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collapse_candidates_lists_duplicate_and_skips_two_items(client, db_session, superadmin_headers, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    root = await _make_category(db_session, subsidy.id, name="Направление")
    dup_cat = await _make_category(db_session, subsidy.id, parent_id=root.id, name="Хозтовары")
    await _make_planned_item(db_session, dup_cat.id, "хозтовары", 1, 300)  # регистр отличается — normalize сравнит равными

    two_cat = await _make_category(db_session, subsidy.id, parent_id=root.id, name="Две позиции")
    await _make_planned_item(db_session, two_cat.id, "Поз. 1", 1, 100)
    await _make_planned_item(db_session, two_cat.id, "Поз. 2", 1, 200)

    resp = await client.get(
        "/api/feo-categories/collapse-candidates", params={"subsidy_id": subsidy.id}, headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    by_cat = {it["category_id"]: it for it in items}

    assert dup_cat.id in by_cat
    assert by_cat[dup_cat.id]["is_name_duplicate"] is True
    assert by_cat[dup_cat.id]["parent_id"] == root.id
    assert by_cat[dup_cat.id]["parent_name"] == "Направление"
    assert by_cat[dup_cat.id]["blocked_reason"] is None

    assert two_cat.id not in by_cat, "категория с двумя активными позициями не должна попадать в кандидаты"


@pytest.mark.asyncio
async def test_collapse_candidates_marks_root_as_blocked(client, db_session, superadmin_headers, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    root = await _make_category(db_session, subsidy.id, name="Корневая-лист")
    await _make_planned_item(db_session, root.id, "Корневая-лист", 1, 500)

    resp = await client.get(
        "/api/feo-categories/collapse-candidates", params={"subsidy_id": subsidy.id}, headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    by_cat = {it["category_id"]: it for it in resp.json()["items"]}
    assert root.id in by_cat
    assert by_cat[root.id]["blocked_reason"] is not None
    assert "родительской категории" in by_cat[root.id]["blocked_reason"]


# ---------------------------------------------------------------------------
# 5) Массовая свёртка: одна ок, одна с ошибкой (ошибка не откатывает первую)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collapse_bulk_one_ok_one_error(client, db_session, superadmin_headers, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    root = await _make_category(db_session, subsidy.id, name="Направление")
    ok_cat = await _make_category(db_session, subsidy.id, parent_id=root.id, name="Бумага")
    ok_item = await _make_planned_item(db_session, ok_cat.id, "Бумага", 1, 400)
    # Плоские id — захватить ДО запроса: обработка missing_cat_id внутри
    # ручки завершается db.rollback() (см. collapse_bulk), а rollback() на
    # AsyncSession экспайрит ВСЕ уже загруженные объекты сессии независимо от
    # expire_on_commit — обращение к ok_cat.id ПОСЛЕ запроса потребовало бы
    # неявной синхронной подгрузки атрибута вне greenlet-контекста (MissingGreenlet).
    ok_cat_id = ok_cat.id
    ok_item_id = ok_item.id

    missing_cat_id = 999_999_999

    resp = await client.post(
        "/api/feo-categories/collapse-bulk",
        json={"category_ids": [ok_cat_id, missing_cat_id]},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    results = {r["category_id"]: r for r in resp.json()["results"]}

    assert results[ok_cat_id]["ok"] is True
    assert results[ok_cat_id]["planned_item_id"] == ok_item_id
    assert results[ok_cat_id]["error"] is None

    assert results[missing_cat_id]["ok"] is False
    assert results[missing_cat_id]["planned_item_id"] is None
    assert "не найдена" in results[missing_cat_id]["error"]

    from app.models.feo_category import FeoCategory
    from sqlalchemy import select
    assert (await db_session.execute(
        select(FeoCategory).where(FeoCategory.id == ok_cat_id)
    )).scalar_one_or_none() is None, "успешная свёртка не должна откатиться из-за ошибки соседней категории"
