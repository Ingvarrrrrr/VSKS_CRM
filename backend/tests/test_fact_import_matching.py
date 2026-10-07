"""Матчинг строки импорта факта → FeoPlannedItem (каскад: имя → сумма плана
→ путь предков → порядок вхождения; без нечёткого сопоставления)."""
import uuid

import pytest

from app.services.historical_fact_import import matching as matching_mod


async def _make_subsidy(db_session, org_id):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"FactImport-Match-{uuid.uuid4().hex[:8]}", year=2026, org_id=org_id)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_leaf_category(db_session, subsidy_id, name, parent_id=None):
    from app.models.feo_category import FeoCategory
    c = FeoCategory(subsidy_id=subsidy_id, parent_id=parent_id, level=3, name=name)
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _make_planned_item(db_session, category_id, name, amount, unit_price=None, quantity=None):
    from app.models.feo_planned_item import FeoPlannedItem
    it = FeoPlannedItem(feo_category_id=category_id, name=name, amount=amount,
                         unit_price=unit_price, quantity=quantity, is_active=True)
    db_session.add(it)
    await db_session.commit()
    await db_session.refresh(it)
    return it


@pytest.mark.asyncio
async def test_exact_name_match(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_leaf_category(db_session, subsidy.id, "Командировочные расходы")
    item = await _make_planned_item(db_session, cat.id, "Командировочные расходы", 80000)

    ctx = await matching_mod.build_matching_context(db_session, subsidy.id)
    row = {"name": "Командировочные расходы", "path": [], "plan": {"amount": 80000}}
    match = matching_mod.match_row(ctx, row)
    assert match["state"] == "found"
    assert match["planned_item_id"] == item.id


@pytest.mark.asyncio
async def test_not_found_when_no_name_match(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_leaf_category(db_session, subsidy.id, "Категория")
    await _make_planned_item(db_session, cat.id, "Совсем другое название", 1000)

    ctx = await matching_mod.build_matching_context(db_session, subsidy.id)
    row = {"name": "Бумага А4", "path": [], "plan": {"amount": 1000}}
    match = matching_mod.match_row(ctx, row)
    assert match["state"] == "not_found"
    assert match["planned_item_id"] is None


@pytest.mark.asyncio
async def test_ambiguous_name_resolved_by_plan_amount(db_session, test_org):
    """Два плановых одного имени в разных категориях — выбирается ближайшая
    по сумме плана (детерминированно, без угадывания)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = await _make_leaf_category(db_session, subsidy.id, "Категория А")
    cat_b = await _make_leaf_category(db_session, subsidy.id, "Категория Б")
    item_a = await _make_planned_item(db_session, cat_a.id, "Заправка топливом", 50000)
    item_b = await _make_planned_item(db_session, cat_b.id, "Заправка топливом", 200000)

    ctx = await matching_mod.build_matching_context(db_session, subsidy.id)
    row = {"name": "Заправка топливом", "path": [], "plan": {"amount": 199000}}
    match = matching_mod.match_row(ctx, row)
    assert match["planned_item_id"] == item_b.id
    assert len(match["candidates"]) == 2


@pytest.mark.asyncio
async def test_duplicate_name_rows_do_not_collapse_onto_one_planned_item(db_session, test_org):
    """РЕЕ-2026-08630: 4 строки файла, одна и та же плановая позиция (план
    50 шт.) в каталоге — только ОДНА штука. Первая строка матчится found,
    остальные НЕ должны схлопнуться на ту же id (иначе план «количество
    набрано вчетверо») — становятся ambiguous (пользователь решает вручную)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_leaf_category(db_session, subsidy.id, "Запчасти")
    item = await _make_planned_item(db_session, cat.id, "Деталь 50 шт.", 50000, quantity=50)

    ctx = await matching_mod.build_matching_context(db_session, subsidy.id)
    row = {"name": "Деталь 50 шт.", "path": [], "plan": {"amount": 50000}}

    m1 = matching_mod.match_row(ctx, row)
    m2 = matching_mod.match_row(ctx, row)
    m3 = matching_mod.match_row(ctx, row)
    m4 = matching_mod.match_row(ctx, row)

    assert m1["state"] == "found"
    assert m1["planned_item_id"] == item.id
    for m in (m2, m3, m4):
        assert m["state"] == "ambiguous"
        assert m["planned_item_id"] is None


@pytest.mark.asyncio
async def test_duplicate_name_rows_consume_distinct_planned_items(db_session, test_org):
    """Когда в плане ЕСТЬ несколько позиций с тем же именем (легитимный
    повтор — несколько одинаковых закупок в плане), каждая строка файла
    получает СВОЙ плановый id, а не одну и ту же."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_leaf_category(db_session, subsidy.id, "Запчасти")
    item1 = await _make_planned_item(db_session, cat.id, "Деталь", 1000)
    item2 = await _make_planned_item(db_session, cat.id, "Деталь", 1000)

    ctx = await matching_mod.build_matching_context(db_session, subsidy.id)
    row = {"name": "Деталь", "path": [], "plan": {"amount": 1000}}

    m1 = matching_mod.match_row(ctx, row)
    m2 = matching_mod.match_row(ctx, row)
    m3 = matching_mod.match_row(ctx, row)

    ids = {m1["planned_item_id"], m2["planned_item_id"]}
    assert ids == {item1.id, item2.id}
    assert m3["state"] == "ambiguous"
    assert m3["planned_item_id"] is None


@pytest.mark.asyncio
async def test_ambiguous_match_reports_competing_row(db_session, test_org):
    """Задание 07.10.2026 (чек-лист, п.2): вторая строка файла на ту же
    плановую позицию получает ambiguous С номером строки, которая заняла
    позицию раньше, и её именем — иначе предупреждение не говорит, на какую
    строку смотреть (owner: «Стр. 16 — какие?»)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_leaf_category(db_session, subsidy.id, "Запчасти")
    item = await _make_planned_item(db_session, cat.id, "Деталь 50 шт.", 50000, quantity=50)

    ctx = await matching_mod.build_matching_context(db_session, subsidy.id)
    row1 = {"row": 10, "name": "Деталь 50 шт.", "path": [], "plan": {"amount": 50000}}
    row2 = {"row": 16, "name": "Деталь 50 шт.", "path": [], "plan": {"amount": 50000}}

    m1 = matching_mod.match_row(ctx, row1)
    m2 = matching_mod.match_row(ctx, row2)

    assert m1["state"] == "found"
    assert m1["planned_item_id"] == item.id
    assert m2["state"] == "ambiguous"
    assert m2["competing_rows"] == [10]
    assert m2["competing_item_name"] == "Деталь 50 шт."


@pytest.mark.asyncio
async def test_already_purchased_planned_item_flagged(db_session, test_org):
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_leaf_category(db_session, subsidy.id, "Категория")
    item = await _make_planned_item(db_session, cat.id, "Ноутбук офисный", 60000)

    purchase = Purchase(subsidy_id=subsidy.id, status="work_in_progress")
    db_session.add(purchase)
    await db_session.flush()
    db_session.add(PurchaseItem(purchase_id=purchase.id, item_name="Ноутбук офисный",
                                 total_price=60000, feo_planned_item_id=item.id))
    await db_session.commit()

    ctx = await matching_mod.build_matching_context(db_session, subsidy.id)
    row = {"name": "Ноутбук офисный", "path": [], "plan": {"amount": 60000}}
    match = matching_mod.match_row(ctx, row)
    assert match["state"] == "already_purchased"
    assert match["planned_item_id"] == item.id
