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
async def test_exact_plan_amount_matched_before_earlier_row(db_session, test_org):
    """Задача A (владелец, боевой файл ХО_ЛНР_ДНР_МАКЛЮК_Отправил.xlsx, лист
    ДНРР, 11.10.2026): план GALA содержит ОДНУ позицию «Проезд, проживание,
    питание» на 292 815,90 ₽. Строка 151 файла (план 407 184,10) идёт раньше
    строки 152 (план 292 815,90), но именно 152 точно совпадает по сумме
    плана — должна получить позицию, 151 — «позиции нет», с указанием, что
    позиция уже сопоставлена строке 152."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_leaf_category(db_session, subsidy.id, "Проезд, проживание, питание")
    item = await _make_planned_item(db_session, cat.id, "Проезд, проживание, питание", 292815.90)

    ctx = await matching_mod.build_matching_context(db_session, subsidy.id)
    row151 = {"row": 151, "name": "Проезд, проживание, питание", "path": [], "plan": {"amount": 407184.10}}
    row152 = {"row": 152, "name": "Проезд, проживание, питание", "path": [], "plan": {"amount": 292815.90}}

    ordered = matching_mod.order_rows_for_matching(ctx, [row151, row152])
    assert [r["row"] for r in ordered] == [152, 151]

    results = {}
    for row in ordered:
        results[row["row"]] = matching_mod.match_row(ctx, row)

    assert results[152]["state"] == "found"
    assert results[152]["planned_item_id"] == item.id
    assert results[151]["state"] == "ambiguous"
    assert results[151]["planned_item_id"] is None
    assert results[151]["competing_rows"] == [152]


@pytest.mark.asyncio
async def test_two_exact_amount_rows_keep_own_planned_items_gsm_regression(db_session, test_org):
    """Регрессия «ГСМ» (боевой файл ХО — см. test_fact_import_rows.py::
    test_total_row_above_two_same_named_positions_is_skipped): две строки
    одноимённой позиции «Расходы на приобретение ГСМ» с планом 413 050,66 и
    286 949,34 — ОБЕ точно совпадают по сумме со своими, РАЗНЫМИ плановыми
    позициями; двухпроходное упорядочивание (Задача A) не должно их
    перепутать независимо от порядка в файле."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_leaf_category(db_session, subsidy.id, "Расходы на приобретение ГСМ")
    item1 = await _make_planned_item(db_session, cat.id, "Расходы на приобретение ГСМ", 413050.66)
    item2 = await _make_planned_item(db_session, cat.id, "Расходы на приобретение ГСМ", 286949.34)

    ctx = await matching_mod.build_matching_context(db_session, subsidy.id)
    row147 = {"row": 147, "name": "Расходы на приобретение ГСМ", "path": [], "plan": {"amount": 413050.66}}
    row148 = {"row": 148, "name": "Расходы на приобретение ГСМ", "path": [], "plan": {"amount": 286949.34}}

    ordered = matching_mod.order_rows_for_matching(ctx, [row147, row148])
    results = {}
    for row in ordered:
        results[row["row"]] = matching_mod.match_row(ctx, row)

    assert results[147]["state"] == "found"
    assert results[148]["state"] == "found"
    assert results[147]["planned_item_id"] == item1.id
    assert results[148]["planned_item_id"] == item2.id


@pytest.mark.asyncio
async def test_shared_group_assigns_all_rows_to_one_planned_item(db_session, test_org):
    """Задача Б (владелец, боевой файл ХО_ЛНР_ДНР_МАКЛЮК_Отправил.xlsx, лист
    ДНРР, 12.10.2026): «Gaz A22R35 Х920АЕ 180» — план GALA содержит ОДНУ
    позицию на 352 400 ₽ (ремонт этой машины), а в файле факта — 4 СТРОКИ с
    тем же именем на 317 400 / 20 000 / 10 000 / 5 000 (Σ = 352 400, точное
    совпадение с планом ОДНОЙ свободной позиции) — КАЖДАЯ строка получает
    эту позицию (found, не ambiguous), shared_item=True, без «позиции нет
    в плане» для трёх из четырёх."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_leaf_category(db_session, subsidy.id, "Ремонт ТС")
    item = await _make_planned_item(db_session, cat.id, "Gaz A22R35 Х920АЕ 180", 352400)

    ctx = await matching_mod.build_matching_context(db_session, subsidy.id)
    rows = [
        {"row": 20, "name": "Gaz A22R35 Х920АЕ 180", "path": [], "plan": {"amount": 317400}},
        {"row": 27, "name": "Gaz A22R35 Х920АЕ 180", "path": [], "plan": {"amount": 20000}},
        {"row": 28, "name": "Gaz A22R35 Х920АЕ 180", "path": [], "plan": {"amount": 10000}},
        {"row": 31, "name": "Gaz A22R35 Х920АЕ 180", "path": [], "plan": {"amount": 5000}},
    ]

    ordered = matching_mod.order_rows_for_matching(ctx, rows)
    results = {row["row"]: matching_mod.match_row(ctx, row) for row in ordered}

    for rn in (20, 27, 28, 31):
        assert results[rn]["state"] == "found", results[rn]
        assert results[rn]["planned_item_id"] == item.id
        assert results[rn]["shared_item"] is True
        assert results[rn]["shared_rows"] == [20, 27, 28, 31]


@pytest.mark.asyncio
async def test_shared_group_does_not_apply_when_sums_mismatch(db_session, test_org):
    """Контроль: 2 строки 407 184,10 / 292 815,90 при ОДНОЙ свободной позиции
    292 815,90 — суммы строк (Σ=700 000) НЕ совпадают с планом позиции,
    поэтому группа НЕ объединяется через shared-механизм — поведение как
    раньше (одна found по точному совпадению суммы, вторая ambiguous), см.
    test_exact_plan_amount_matched_before_earlier_row."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_leaf_category(db_session, subsidy.id, "Проезд, проживание, питание")
    item = await _make_planned_item(db_session, cat.id, "Проезд, проживание, питание", 292815.90)

    ctx = await matching_mod.build_matching_context(db_session, subsidy.id)
    row151 = {"row": 151, "name": "Проезд, проживание, питание", "path": [], "plan": {"amount": 407184.10}}
    row152 = {"row": 152, "name": "Проезд, проживание, питание", "path": [], "plan": {"amount": 292815.90}}

    ordered = matching_mod.order_rows_for_matching(ctx, [row151, row152])
    results = {row["row"]: matching_mod.match_row(ctx, row) for row in ordered}

    assert results[152]["state"] == "found"
    assert results[152]["planned_item_id"] == item.id
    assert not results[152].get("shared_item")
    assert results[151]["state"] == "ambiguous"


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
