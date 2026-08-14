"""Автотесты на `_do_feo_import` (backend/app/routers/feo_categories.py, ~стр. 1567)
после переписи под новый 18-колоночный шаблон (2026-08-14).

`_do_feo_import` вызывается НАПРЯМУЮ списком строк (xlsx/HTTP не нужны) — колонки
задаются индексами через `c_*`-параметры. Тесты собирают свой собственный
18-колоночный макет строки через `mk_row(...)` (см. `ROW_FIELDS`/`IMPORT_KWARGS`
ниже) и передают его через `default_subsidy_id`, минуя колонку «Субсидия».

Каждый тест создаёт СВОЮ субсидию (уникальное имя `TestFeoImport-...`) и в
finally вычищает всё, что создал (позиции → категории → субсидия) — локальная
БД разработчика не должна замусориваться.

ВАЖНО (известная особенность проекта): async-тесты в этом файле падают с
«different loop», если запускать 2+ штук в одном вызове pytest. Гонять по
одному: `python -m pytest tests/test_feo_import_tree.py::<имя> -x -q`.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.routers.feo_categories import _do_feo_import
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem


# --- Макет 18-колоночной тестовой строки -----------------------------------
# Индексы произвольные (мы полностью управляем c_*-параметрами вызова), но
# сама раскладка соответствует новому шаблону: «плоские» числа по ФЭО/плану —
# ОДНА пара колонок на строку (не по уровням), плюс одна per-level колонка
# (amt_lvl2) — специально для сценария «имя уровня в числовой колонке».
ROW_FIELDS = [
    "lvl2", "lvl3", "lvl4", "item_name", "item_type", "code", "appendix",
    "budget", "active", "feo_qty", "feo_unit", "feo_price", "feo_sum",
    "plan_qty", "plan_unit", "plan_price", "plan_sum", "amt_lvl2",
]

_IDX = {name: i for i, name in enumerate(ROW_FIELDS)}


def mk_row(**kwargs):
    unknown = set(kwargs) - set(ROW_FIELDS)
    assert not unknown, f"неизвестные поля строки: {unknown}"
    row = [None] * len(ROW_FIELDS)
    for k, v in kwargs.items():
        row[_IDX[k]] = v
    return row


async def _make_subsidy(db_session, budget=0):
    s = Subsidy(
        name=f"TestFeoImport-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _cleanup_subsidy(db_session, subsidy_id):
    """Убирает за собой всё, что мог создать импорт: позиции → категории →
    саму субсидию. Явные DELETE, не полагаемся на ON DELETE CASCADE."""
    await db_session.execute(text(
        "DELETE FROM feo_planned_items WHERE feo_category_id IN "
        "(SELECT id FROM feo_categories WHERE subsidy_id = :sid)"
    ), {"sid": subsidy_id})
    await db_session.execute(text(
        "DELETE FROM feo_categories WHERE subsidy_id = :sid"
    ), {"sid": subsidy_id})
    await db_session.execute(text(
        "DELETE FROM subsidies WHERE id = :sid"
    ), {"sid": subsidy_id})
    await db_session.commit()


async def _get_categories(db_session, subsidy_id):
    res = await db_session.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )
    return res.scalars().all()


async def _get_items(db_session, feo_category_id):
    res = await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == feo_category_id)
    )
    return res.scalars().all()


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
        db=db_session,
    )


# --- 1. Плановая позиция не создаёт папку -----------------------------------

@pytest.mark.asyncio
async def test_planned_item_does_not_create_own_category(db_session):
    """Ур.2/Ур.3 + «Плановая позиция» с планом → создаются ДВЕ категории и ОДНА
    FeoPlannedItem внутри листа; категории с именем позиции НЕТ."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Прочие расходы", lvl3="Расходы на ремонт ТС",
            item_name="УАЗ Патриот У914ВН 180", item_type="Товар",
            plan_qty="1", plan_unit="усл", plan_price="178779.59", plan_sum="178779.59",
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        assert set(by_name) == {"Прочие расходы", "Расходы на ремонт ТС"}, (
            "категории «УАЗ Патриот У914ВН 180» быть не должно"
        )
        root, leaf = by_name["Прочие расходы"], by_name["Расходы на ремонт ТС"]
        assert root.parent_id is None and root.level == 1
        assert leaf.parent_id == root.id and leaf.level == 2

        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        item = items[0]
        assert item.name == "УАЗ Патриот У914ВН 180"
        assert item.item_type == "товар"
        assert item.amount == Decimal("178779.59")
        assert item.feo_category_id == leaf.id
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 2. Числа по ФЭО идут последнему заполненному уровню --------------------

@pytest.mark.asyncio
async def test_feo_sum_goes_to_deepest_filled_level(db_session):
    """Ур.2=A, Ур.3=B, Сумма по ФЭО=2000000 → budget=2 000 000 у B, у A пуст."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(lvl2="Направление A2", lvl3="Категория B2", feo_sum="2000000")]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        a, b = by_name["Направление A2"], by_name["Категория B2"]
        assert b.parent_id == a.id
        assert b.budget == Decimal("2000000")
        assert a.budget is None
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 3. План у категории (без «Плановая позиция») ---------------------------

@pytest.mark.asyncio
async def test_plan_without_item_column_names_item_after_category(db_session):
    """Строка с плановыми числами и БЕЗ «Плановая позиция» → FeoPlannedItem с
    именем самой (листовой) категории — прежнее поведение."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Направление C3", lvl3="Категория D3",
            plan_qty="2", plan_unit="шт", plan_price="1000", plan_sum="2000",
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Категория D3")

        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        item = items[0]
        assert item.name == "Категория D3"
        assert item.quantity == Decimal("2")
        assert item.amount == Decimal("2000")
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 4. Позиция без уровней → Ур.2 ------------------------------------------

@pytest.mark.asyncio
async def test_item_without_any_level_promoted_to_level2(db_session):
    """Ур.2/3/4 пусты, «Плановая позиция» заполнена → КАТЕГОРИЯ уровня 1 с этим
    именем + warning item_promoted_to_level2; сама позиция НЕ создаётся."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(item_name="Заголовок без уровня E4")]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert any(w["kind"] == "item_promoted_to_level2" for w in result["warnings"])

        cats = await _get_categories(db_session, subsidy.id)
        assert len(cats) == 1
        cat = cats[0]
        assert cat.name == "Заголовок без уровня E4"
        assert cat.level == 1
        assert cat.parent_id is None

        items = await _get_items(db_session, cat.id)
        assert items == []
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 5. Название уровня в числовой колонке -----------------------------------

@pytest.mark.asyncio
async def test_level_name_recovered_from_number_column(db_session):
    """Имя уровня 3 стоит в числовой колонке уровня 2 (amt_lvl2), Ур.3 пуст,
    Ур.4 заполнен напрямую → имя становится Уровнем 3, путь
    A / <восстановленное имя> / <Ур.4>, warning level_name_in_number_column,
    БЕЗ спутнического level_gap (это и есть боевой дефект, ради которого всё
    затевалось: раньше Ур.4 «поджимался» прямо к Ур.2, минуя пропавший Ур.3)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Направление F5",
            lvl4="Материалы для ремонта F5",
            amt_lvl2="Расходы на содержание и ремонт ТС F5",
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert any(w["kind"] == "level_name_in_number_column" for w in result["warnings"])
        assert not any(w["kind"] == "level_gap" for w in result["warnings"]), (
            "восстановленный Ур.3 не должен считаться пропущенным уровнем"
        )

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        assert set(by_name) == {
            "Направление F5",
            "Расходы на содержание и ремонт ТС F5",
            "Материалы для ремонта F5",
        }
        root = by_name["Направление F5"]
        mid = by_name["Расходы на содержание и ремонт ТС F5"]
        leaf = by_name["Материалы для ремонта F5"]
        assert root.level == 1 and root.parent_id is None
        assert mid.level == 2 and mid.parent_id == root.id
        assert leaf.level == 3 and leaf.parent_id == mid.id
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 6. Идемпотентность ------------------------------------------------------

@pytest.mark.asyncio
async def test_reimport_same_rows_is_idempotent(db_session):
    """Прогон тех же строк (сценарий 1) дважды → второй раз новых категорий и
    позиций не появляется, дублей нет."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Прочие расходы G6", lvl3="Расходы на ремонт ТС G6",
            item_name="УАЗ Патриот G6", item_type="Товар",
            plan_qty="1", plan_unit="усл", plan_price="178779.59", plan_sum="178779.59",
        )]

        result1 = await _import(db_session, subsidy.id, rows)
        assert result1["errors"] == []
        cats1 = await _get_categories(db_session, subsidy.id)
        assert len(cats1) == 2
        leaf1 = next(c for c in cats1 if c.name == "Расходы на ремонт ТС G6")
        items1 = await _get_items(db_session, leaf1.id)
        assert len(items1) == 1

        result2 = await _import(db_session, subsidy.id, rows)
        assert result2["errors"] == []
        assert result2["created"] == 0, "повторный импорт не должен создавать новые категории/позиции"

        cats2 = await _get_categories(db_session, subsidy.id)
        assert len(cats2) == 2, "дублей категорий быть не должно"
        leaf2 = next(c for c in cats2 if c.name == "Расходы на ремонт ТС G6")
        items2 = await _get_items(db_session, leaf2.id)
        assert len(items2) == 1, "дублей плановой позиции быть не должно"
        assert items2[0].amount == Decimal("178779.59")
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 7. Пропущенный уровень поджимается (старое поведение не сломано) -------

@pytest.mark.asyncio
async def test_level_gap_still_collapses_when_no_number_column_involved(db_session):
    """Ур.2=A, Ур.3 пусто, Ур.4=C (без «имени в числовой колонке») → путь A / C,
    warning level_gap — старое поведение осталось нетронутым правкой #5."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(lvl2="Направление H7", lvl4="Статья H7")]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert any(w["kind"] == "level_gap" for w in result["warnings"])

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        assert set(by_name) == {"Направление H7", "Статья H7"}
        root, leaf = by_name["Направление H7"], by_name["Статья H7"]
        assert root.level == 1 and root.parent_id is None
        assert leaf.level == 2 and leaf.parent_id == root.id
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 8. Честная формулировка plan_vs_items_mismatch при фолбэке на числа ФЭО

@pytest.mark.asyncio
async def test_plan_vs_items_mismatch_warns_when_amount_from_feo_fallback(db_session):
    """Плановых кол-ва/цены в файле нет вообще — план строки посчитан старым
    фолбэком из чисел «по ФЭО» (feo_qty × feo_price). У той же категории в этом
    же импорте есть своя позиция Ур.5 с другой суммой → warning
    plan_vs_items_mismatch должен честно указывать, что сумма плана строки
    взята из чисел по ФЭО, а не из (пустых) плановых колонок."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Направление I8", lvl3="Категория I8",
            feo_qty="2", feo_price="400000",  # план строки = 800 000, фолбэк
            item_name="Позиция I8",  # своя сумма Ур.5 = 0 (не задана) → расхождение
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        mismatches = [w for w in result["warnings"] if w["kind"] == "plan_vs_items_mismatch"]
        assert len(mismatches) == 1
        msg = mismatches[0]["message"]
        assert "Категория I8" in msg
        assert "(взят из чисел по ФЭО, плановые колонки пустые)" in msg
        assert "800 000.00" in msg
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
