"""Решения владельца 22.10.2026 (боевой инцидент, субсидия ДНР_2026 id 105):

  1) Суммы из файла — до копеек ДО сравнения/записи (см. app.services.
     feo_import_common.to_dec_money) — Excel хранит формулу кол-во×цена как
     float (50×34,2 = 1710.0000000000002), и _upsert_one сравнивал это сырое
     число с уже округлённым Decimal('1710.00') из БД — каждый повторный
     импорт того же файла давал ложное «обновлено» и лишнюю запись истории.

  2) Повторный импорт той же строки листа (source_row) в ДРУГУЮ статью —
     ПЕРЕНОС существующей позиции (см. app.services.feo_import_duplicates.
     _find_transfer_candidate), а не вторая позиция — строки 253/254 файла
     ДНР_2026 задвоили план на 16 500, потому что вторая загрузка создала их
     ЕЩЁ РАЗ в другой подстатье.

  3) app.services.feo_item_source_duplicates — то же правило совпадения
     (source_row + нормализованное имя в РАЗНЫХ статьях), вынесенное для
     признака `source_duplicates` экрана (GET /api/feo-categories/plan-positions).

Харнесс (mk_row/_IDX/_make_subsidy/_get_categories/_get_items/_cleanup_subsidy)
— тот же, что в test_feo_import_tree.py/test_feo_import_source_row.py (Правило
№6, не второй макет строки). ВАЖНО: гонять тесты этого файла по одному
(известная особенность проекта — «different loop» при 2+ async-тестах в одном
вызове pytest, см. test_feo_import_tree.py)."""
import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.entity_change import EntityChange
from app.models.feo_planned_item import FeoPlannedItem
from app.routers.feo_categories import _do_feo_import
from app.services import feo_history
from app.services.feo_import_duplicates import group_key
from app.services.feo_item_source_duplicates import find_source_row_duplicates
from tests.test_feo_import_tree import _IDX, _cleanup_subsidy, _get_categories, _get_items, _make_subsidy, mk_row


async def _import(db_session, subsidy_id, rows):
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
        dry_run=False,
        db=db_session,
    )


async def _import_merge(db_session, subsidy_id, rows, resolution_key):
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
        dry_run=False,
        db=db_session,
        duplicate_resolutions=json.dumps({resolution_key: "merge"}),
    )


@pytest.mark.asyncio
async def test_repeated_import_of_merged_group_is_a_noop(db_session):
    """РЕГРЕССИЯ (найдена координатором): `_upsert_merge` ВСЕГДА передаёт свой
    `extra_reason` («объединено из N строк…») в `_upsert_one` — старое условие
    `ch2 or extra_reason is not None` считало это «обновлено» даже когда
    повторный импорт ТОГО ЖЕ файла ничего не меняет. Группа из 2 строк с
    решением 'merge' — второй импорт того же файла обязан дать `updated == 0`
    (владелец: повторный импорт того же листа = «Обновлено: 0»)."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        rows = [
            mk_row(lvl2="Кухня", item_name="Чайник", plan_qty="1", plan_price="4000"),
            mk_row(lvl2="Кухня", item_name="Чайник", plan_qty="1", plan_price="5000"),
        ]
        key = group_key(subsidy_id, ["Кухня"], "Чайник")

        await _import_merge(db_session, subsidy_id, rows, key)
        cats = await _get_categories(db_session, subsidy_id)
        kitchen = next(c for c in cats if c.name == "Кухня")
        items1 = await _get_items(db_session, kitchen.id)
        assert len(items1) == 1
        assert items1[0].amount == Decimal("9000.00")

        r2 = await _import_merge(db_session, subsidy_id, rows, key)
        assert r2["updated"] == 0

        items2 = await _get_items(db_session, kitchen.id)
        assert len(items2) == 1
        assert items2[0].id == items1[0].id
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


@pytest.mark.asyncio
async def test_repeated_import_of_formula_amount_is_a_noop(db_session):
    """(а) Сумма — результат формулы Excel кол-во×цена (50×34,2), в float это
    1710.0000000000002. Повторный импорт ТОГО ЖЕ файла не должен давать
    «обновлено»/лишнюю запись истории — только округление до копеек ДО
    сравнения (to_dec_money) делает Decimal('1710.00') == Decimal('1710.00')."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        _formula_sum = 50 * 34.2  # 1710.0000000000002 (двоичный float)
        rows = [mk_row(lvl2="Кухня", item_name="Чайник", plan_sum=_formula_sum)]

        await _import(db_session, subsidy_id, rows)

        cats = await _get_categories(db_session, subsidy_id)
        kitchen = next(c for c in cats if c.name == "Кухня")
        item_before = (await _get_items(db_session, kitchen.id))[0]
        assert item_before.amount == Decimal("1710.00")

        r2 = await _import(db_session, subsidy_id, rows)
        assert r2["updated"] == 0
        assert r2["skipped"] == 1

        items_after = await _get_items(db_session, kitchen.id)
        assert len(items_after) == 1
        assert items_after[0].amount == Decimal("1710.00")

        # Единственная запись истории — создание позиции ПЕРВЫМ импортом;
        # повторный импорт того же файла не добавил ни одной новой строки
        # (без округления до копеек ДО сравнения второй импорт добавлял бы
        # запись "обновлено" с полями amount: 1710.00 -> 1710.0000000000002).
        history_rows = (await db_session.execute(
            select(EntityChange).where(
                EntityChange.entity_type == feo_history.ENTITY_FEO_ITEM,
                EntityChange.entity_id == items_after[0].id,
            )
        )).scalars().all()
        assert len(history_rows) == 1
        assert history_rows[0].field_name == feo_history.FIELD_CREATED_MARKER
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


@pytest.mark.asyncio
async def test_reimport_same_row_into_other_category_moves_item(db_session):
    """(б) Строка файла (source_row=2) импортирована в статью «Расходы на
    приобретение основных средств», затем ТОТ ЖЕ файл (то же имя/source_row)
    импортирован со статьёй-подкатегорией «Бытовая техника» — позиция ОДНА,
    переехала в «Бытовую технику», а не задвоилась (боевой случай «Чайник
    электрический»/«Термопот», ДНР_2026 id 105)."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        await _import(db_session, subsidy_id, [
            mk_row(lvl2="Расходы на приобретение основных средств", item_name="Чайник электрический", plan_sum="1500"),
        ])
        cats1 = await _get_categories(db_session, subsidy_id)
        cat_a = next(c for c in cats1 if c.name == "Расходы на приобретение основных средств")
        items_a = await _get_items(db_session, cat_a.id)
        assert len(items_a) == 1
        assert items_a[0].source_row == 2

        r2 = await _import(db_session, subsidy_id, [
            mk_row(lvl2="Расходы на приобретение основных средств", lvl3="Бытовая техника", item_name="Чайник электрический", plan_sum="1500"),
        ])

        cats2 = await _get_categories(db_session, subsidy_id)
        cat_a2 = next(c for c in cats2 if c.name == "Расходы на приобретение основных средств")
        cat_b = next(c for c in cats2 if c.name == "Бытовая техника")

        items_a_after = await _get_items(db_session, cat_a2.id)
        items_b_after = await _get_items(db_session, cat_b.id)
        assert items_a_after == []
        assert len(items_b_after) == 1
        assert items_b_after[0].id == items_a[0].id  # та же позиция, не новая
        assert items_b_after[0].feo_category_id == cat_b.id

        _reasons = [d["reason"] for d in r2["updated_details"]]
        assert any("перенесена из «Расходы на приобретение основных средств»" in r for r in _reasons)
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


@pytest.mark.asyncio
async def test_source_duplicates_screen_marker(db_session):
    """(в) `find_source_row_duplicates` — две активные позиции с одним
    source_row и одним именем в РАЗНЫХ статьях получают по одному элементу
    друг на друга; разные имена при одном source_row — пусто (это не тот же
    случай «строка листа»)."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        await _import(db_session, subsidy_id, [
            mk_row(lvl2="Статья А", item_name="Молоток", plan_sum="100"),
        ])
        # Собственной рукой заводим вторую активную позицию с тем же
        # source_row/именем в ДРУГОЙ статье — имитирует позицию, которую
        # перенос (п.2 выше) НЕ нашёл бы (например, созданную до этой правки).
        cats = await _get_categories(db_session, subsidy_id)
        cat_a = next(c for c in cats if c.name == "Статья А")
        item_a = (await _get_items(db_session, cat_a.id))[0]
        assert item_a.source_row == 2

        from app.models.feo_category import FeoCategory
        cat_b = FeoCategory(name="Статья Б", subsidy_id=subsidy_id, parent_id=None, level=1, is_active=True)
        db_session.add(cat_b)
        await db_session.flush()
        dup_item = FeoPlannedItem(
            feo_category_id=cat_b.id, name="Молоток", amount=Decimal("100.00"),
            is_active=True, source_row=2,
        )
        other_name_item = FeoPlannedItem(
            feo_category_id=cat_b.id, name="Отвёртка", amount=Decimal("50.00"),
            is_active=True, source_row=2,
        )
        db_session.add_all([dup_item, other_name_item])
        await db_session.commit()
        await db_session.refresh(dup_item)
        await db_session.refresh(other_name_item)

        result = await find_source_row_duplicates(db_session, subsidy_id)

        assert result.get(item_a.id) == [
            {"item_id": dup_item.id, "category_id": cat_b.id, "category_name": "Статья Б"},
        ]
        assert result.get(dup_item.id) == [
            {"item_id": item_a.id, "category_id": cat_a.id, "category_name": "Статья А"},
        ]
        # «Отвёртка» — другое имя, тот же source_row: не дубль ни с кем.
        assert other_name_item.id not in result
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)
