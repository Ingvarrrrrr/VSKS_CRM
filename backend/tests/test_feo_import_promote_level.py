"""Автотесты на продвижение «Плановой позиции» в уровень (задача владельца
2026-09-09, план dreamy-booping-piglet.md, задача A) — `_do_feo_import`
(backend/app/routers/feo_categories.py) через feo_import_apply.py/
feo_import_plan.py.

Боевой файл владельца («ЦЕНТРПОИСК_ВСКС...xlsx», 17 колонок) НЕ содержит
колонку «Уровень 4» — используем `_import17`, копию `_import` из
test_feo_import_tree.py, но с `c_lvl4=None`, чтобы воспроизвести ровно ту же
раскладку уровней (иначе поиск «ближайшего пустого размеченного уровня»
находил бы несуществующий в файле владельца Ур.4 первым и давал другой
результат, чем на проде).

ВАЖНО (известная особенность проекта): async-тесты в этом файле падают с
«different loop», если запускать 2+ штук в одном вызове pytest. Гонять по
одному: `python -m pytest tests/test_feo_import_promote_level.py::<имя> -x -q`.
"""
from decimal import Decimal

import pytest

from app.routers.feo_categories import _do_feo_import
from tests.test_feo_import_tree import (
    _IDX, _cleanup_subsidy, _get_categories, _get_items, _make_subsidy, mk_row,
)


async def _import17(db_session, subsidy_id, rows):
    """Как `_import` из test_feo_import_tree.py, но c_lvl4=None — воспроизводит
    17-колоночный шаблон боевого файла владельца (колонки «Уровень 4» нет)."""
    return await _do_feo_import(
        rows=rows,
        c_subsidy=None,
        c_lvl2=_IDX["lvl2"], c_lvl3=_IDX["lvl3"], c_lvl4=None, c_lvl5=_IDX["item_name"],
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


# --- Строка 2: Уровень 2 = Плановая позиция = «Экипировка» → схлопывание ----

@pytest.mark.asyncio
async def test_row2_style_reflexive_direction_collapses_to_own_budget(db_session):
    """Строка-заголовок направления (Ур.2 = «Экипировка», Ур.3 пуст, «Плановая
    позиция» = тем же текстом «Экипировка», Сумма по ФЭО = 12 041 760) не
    должна создать отдельную позицию «Экипировка» внутри самой себя —
    продвижение переносит имя на пустой Ур.3, а существующий deduped схлопывает
    Ур.2/Ур.3 обратно в ОДИН узел (боевой дефект: раньше бюджет направления
    «Экипировка» подхватывался последней попавшейся строкой — 100 000 вместо
    12 041 760)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Экипировка", item_name="Экипировка",
            feo_sum="12041760", plan_qty="12041.76",
        )]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        assert len(cats) == 1, "Ур.2 и продвинутый Ур.3 обязаны схлопнуться в один узел"
        root = cats[0]
        assert root.name == "Экипировка"
        assert root.level == 1 and root.parent_id is None
        assert root.budget == Decimal("12041760")

        items = await _get_items(db_session, root.id)
        assert items == [], "рефлексивная «Плановая позиция» не должна стать своей же дочерней позицией"
        assert any(w["kind"] == "item_promoted_to_level" for w in result["warnings"])
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- Строки 3/9/24: три ребёнка «Экипировки», бюджет родителя не перезаписан

@pytest.mark.asyncio
async def test_three_children_promoted_to_level3_sum_matches_parent(db_session):
    """Три строки-заголовка подкатегорий (Ур.3 пуст, «Плановая позиция» =
    название подкатегории, своя Сумма по ФЭО) продвигаются на Ур.3 каждая
    отдельным узлом; сумма их бюджетов = бюджету родителя → parent_sum_mismatch
    не выдаётся (боевой дефект: раньше только ПОСЛЕДНЯЯ из таких строк
    «выигрывала» бюджет направления, две другие суммы терялись)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(lvl2="Экипировка", item_name="Экипировка", feo_sum="12041760", plan_qty="12041.76"),
            mk_row(lvl2="Экипировка", item_name="Комплект СИЗ для добровольцев", feo_sum="7941760", plan_qty="1"),
            mk_row(lvl2="Экипировка", item_name="СИЗ спецназначения", feo_sum="4000000", plan_qty="50"),
            mk_row(lvl2="Экипировка", item_name="Одноразовые СИЗ", feo_sum="100000", plan_qty="100"),
        ]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        assert len(cats) == 4, "направление + 3 дочерние категории"
        root = by_name["Экипировка"]
        assert root.budget == Decimal("12041760")
        children = [c for c in cats if c.parent_id == root.id]
        assert len(children) == 3
        budgets = sorted(c.budget for c in children)
        assert budgets == sorted([Decimal("7941760"), Decimal("4000000"), Decimal("100000")])

        assert not any(w["kind"] == "parent_sum_mismatch" for w in result["warnings"]), (
            "сумма дочерних бюджетов совпадает с бюджетом направления — ложного расхождения быть не должно"
        )
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- Строка 33: Ур.2 пуст, Ур.3 заполнен тем же текстом, что «Плановая позиция»

@pytest.mark.asyncio
async def test_row33_style_missing_level2_creates_category_not_dropped(db_session):
    """Ур.2 пуст, Ур.3 = «Транспорт и техника», «Плановая позиция» = тем же
    текстом, Сумма по ФЭО = 29 000 000 — раньше строка целиком отбрасывалась
    гейтом `if not lvl2_name` (условие продвижения на Ур.2 в
    item_promoted_to_level2 требует ПУСТОГО Ур.3, а он заполнен) и сумма
    терялась без единого предупреждения о сумме. Теперь: ближайший пустой
    размеченный уровень — Ур.2 (первый в порядке 2→3→4), деньги есть →
    продвижение переносит имя на Ур.2, схлопывается с Ур.3 (то же имя) в ОДИН
    корневой узел с бюджетом 29 000 000; amount_without_level2 не выдаётся."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl3="Транспорт и техника", item_name="Транспорт и техника",
            feo_sum="29000000",
        )]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert not any(w["kind"] == "amount_without_level2" for w in result["warnings"]), (
            "29 000 000 больше не должны молча теряться"
        )

        cats = await _get_categories(db_session, subsidy.id)
        assert len(cats) == 1
        root = cats[0]
        assert root.name == "Транспорт и техника"
        assert root.level == 1 and root.parent_id is None
        assert root.budget == Decimal("29000000")
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- Строка 251: категория без единого заполненного уровня + 3 рефлексивных ребёнка

@pytest.mark.asyncio
async def test_row251_style_children_keep_own_budget_sum_matches_parent(db_session):
    """«Расходные материалы» (Ур.2 и Ур.3 ОБА пусты, только «Плановая позиция»
    + Сумма по ФЭО = 4 600 000) продвигается на Ур.2. Три дочерние категории
    называют СЕБЯ ЖЕ в «Плановой позиции» (Ур.2 и Ур.3 у них уже заполнены,
    продвигать некуда) — это не отдельные позиции, а итоговые суммы для уже
    заполненного Ур.3: 1 500 000 + 1 000 000 + 2 100 000 = 4 600 000, без
    расхождения и без лишних FeoPlannedItem с именем своей же категории."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(item_name="Расходные материалы", feo_sum="4600000"),
            mk_row(
                lvl2="Расходные материалы", lvl3="Канцелярские и бытовые расходы",
                item_name="Канцелярские и бытовые расходы", feo_sum="1500000",
                plan_qty="1", plan_unit="ед",
            ),
            mk_row(
                lvl2="Расходные материалы", lvl3="Сувенирная продукция",
                item_name="Сувенирная продукция", feo_sum="1000000",
                plan_qty="1000", plan_unit="ед.",
            ),
            mk_row(
                lvl2="Расходные материалы", lvl3="Аренда офиса",
                item_name="Аренда офиса", feo_sum="2100000",
                plan_qty="6.66",
            ),
        ]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        assert len(cats) == 4
        root = by_name["Расходные материалы"]
        assert root.budget == Decimal("4600000")

        canc = by_name["Канцелярские и бытовые расходы"]
        souv = by_name["Сувенирная продукция"]
        office = by_name["Аренда офиса"]
        assert canc.budget == Decimal("1500000")
        assert souv.budget == Decimal("1000000")
        assert office.budget == Decimal("2100000")

        for child in (canc, souv, office):
            items = await _get_items(db_session, child.id)
            assert items == [], (
                f"«{child.name}» назвала себя же в «Плановой позиции» — это итог "
                "уровня, а не отдельная позиция"
            )

        assert not any(w["kind"] == "parent_sum_mismatch" for w in result["warnings"])
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- Строка 188: настоящая позиция с суммой внутри уже занятой категории ----

@pytest.mark.asyncio
async def test_row188_style_item_amount_does_not_overwrite_parent_budget(db_session):
    """Категория «Аренда автотранспортных средств...» уже получила СВОЙ бюджет
    (500 000, строка-заголовок с тем же текстом в Ур.3 и «Плановой позиции»).
    Следующая строка — настоящая позиция («Аренда Хендей ГрандСтарекс», имя
    ≠ имени категории) со своей Суммой по ФЭО (142 500), при этом плановые
    колонки строки — нулевые заглушки. Раньше «Сумма по ФЭО» такой строки
    безусловно уходила в cat.budget, ЗАТИРАЯ 500 000 → 142 500 (реальный
    боевой дефект). Теперь это сумма ПОЗИЦИИ (жёсткая расшифровка,
    is_feo_breakdown), бюджет родителя не тронут."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(
                lvl2="Логистика и проживание", lvl3="Аренда автотранспортных средств",
                item_name="Аренда автотранспортных средств", feo_sum="500000",
                plan_qty="1", plan_unit="услуга",
            ),
            mk_row(
                lvl2="Логистика и проживание", lvl3="Аренда автотранспортных средств",
                item_name="Аренда Хендей ГрандСтарекс", feo_sum="142500",
                plan_qty="15", plan_unit="дней", plan_price="0", plan_sum="0",
            ),
        ]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Аренда автотранспортных средств")
        assert leaf.budget == Decimal("500000"), "бюджет категории не должен затираться суммой позиции"

        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        item = items[0]
        assert item.name == "Аренда Хендей ГрандСтарекс"
        assert item.amount == Decimal("142500"), (
            "сумма позиции берётся из «Суммы по ФЭО» строки, а не из нулевой Суммы плана"
        )
        if hasattr(item, "is_feo_breakdown"):
            assert item.is_feo_breakdown is True
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- Негатив: позиция без суммы при недостающем уровне остаётся не продвинутой

@pytest.mark.asyncio
async def test_item_without_money_and_partial_levels_is_not_promoted(db_session):
    """Ур.2 пуст, Ур.3 заполнен, «Плановая позиция» заполнена, но по строке НЕТ
    ни «Суммы по ФЭО», ни какой-либо другой денежной колонки — продвигать
    нечего (условие явно требует _row_feo_money() is not None), а старая ветка
    item_promoted_to_level2 тоже не подходит (она требует ПОЛНОСТЬЮ пустых
    Ур.2/3/4, а Ур.3 здесь заполнен). Строка просто пропускается — ни новой
    категории, ни новой позиции с этим именем быть не должно."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(lvl3="Уже существующий уровень", item_name="Позиция без суммы")]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert not any(w["kind"] == "item_promoted_to_level" for w in result["warnings"])

        cats = await _get_categories(db_session, subsidy.id)
        assert cats == [], "без суммы и без Ур.2 строка не должна создать ни одной категории"
        assert len(result["skipped_details"]) == 1
        assert result["skipped_details"][0]["reason"] == "нет наименования (уровень 2 пуст)"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
