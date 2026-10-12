"""Боевой инцидент 2026-09-16 (субсидия «Абхазия_2», файл «Абхазия ЦЭМАК»):
189 позиций Ур.5 с is_feo_breakdown=true, но их feo_quantity/feo_unit_price/
feo_amount (см. FeoPlannedItem, миграция c2d4e6f8a0b2) не заполнялись импортом
вовсе, а unit_price позиции не заполнялся никогда — карточка субсидии
показывала «по ФЭО» в разы меньше реальной суммы 189 позиций.

Три сценария (feo_import_apply.py, блок «плоские числа нового 18-колоночного
шаблона» — c_row_feo_*/c_row_plan_*):
  1. У строки заданы ОБА комплекта (ФЭО ≠ план) — позиция обязана хранить их
     РАЗДЕЛЬНО (quantity/unit_price/amount = план, feo_quantity/feo_unit_price/
     feo_amount = ФЭО), а не сливать в один набор (что раньше молча теряло
     плановые числа, если ФЭО-колонки шли первыми).
  2. У строки задан ТОЛЬКО ФЭО (плановых колонок нет вовсе) — план позиции
     считается РАВНЫМ ФЭО (решение владельца, «если плановых нет, а ФЭО есть —
     план = ФЭО»), обе галочки происхождения выставлены resolve_origin_flags.
  3. Строка 189 «Катер»: имя позиции = имя подраздела Ур.4, лежащего глубже
     файлового разрыва (Ур.2 пуст) — подраздел получает бюджет как раньше,
     позиция с тем же именем тоже заводится (apply_collected_plan), но теперь
     ЧЕЛОВЕК должен узнать об этом совпадении — `item_name_equals_category`.

Гоняется по одному тесту (см. предупреждение в test_feo_import_tree.py про
async «different loop»): `python -m pytest
tests/test_feo_import_item_feo_split.py::<имя> -x -q`.
"""
from decimal import Decimal

import pytest

from tests.test_feo_import_tree import (
    _cleanup_subsidy, _get_categories, _get_items, _import, _make_subsidy, mk_row,
)


@pytest.mark.asyncio
async def test_item_feo_and_plan_numbers_stay_separate(db_session):
    """ФЭО (3 шт × 7990 = 23970) и план РАЗНЫЕ (2 шт × 8000 = 16000) на одной
    строке — FeoPlannedItem обязан хранить оба комплекта раздельно, не сливая
    их и не теряя один из них."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl3="Оборудование и снаряжение", lvl4="Альпинистское снаряжение",
            item_name="Спусковое устройство Венто Стопор-десантер", item_type="Товар",
            feo_qty="3", feo_unit="шт.", feo_price="7990", feo_sum="23970",
            plan_qty="2", plan_unit="шт.", plan_price="8000", plan_sum="16000",
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Альпинистское снаряжение")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        item = items[0]

        # План (участвует в дереве плана/контроле превышения) — из плановых колонок.
        assert item.quantity == Decimal("2")
        assert item.unit == "шт."
        assert item.unit_price == Decimal("8000")
        assert item.amount == Decimal("16000")

        # ФЭО (сверка/witness, см. докстринг FeoPlannedItem.feo_quantity) — из ФЭО-колонок.
        assert item.feo_quantity == Decimal("3")
        assert item.feo_unit_price == Decimal("7990")
        assert item.feo_amount == Decimal("23970")
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_item_plan_falls_back_to_feo_when_plan_columns_empty(db_session):
    """Плановых колонок у строки нет вовсе (боевой случай — большинство из 189
    строк «Абхазия ЦЭМАК») — план позиции = числа по ФЭО (владелец: «если
    плановых нет, а ФЭО есть — план = ФЭО»), is_feo_breakdown=True."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl3="Оборудование и снаряжение", lvl4="Альпинистское снаряжение",
            item_name="Спусковое устройство Венто Стопор-десантер", item_type="Товар",
            feo_qty="3", feo_unit="шт.", feo_price="7990", feo_sum="23970",
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Альпинистское снаряжение")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        item = items[0]

        assert item.quantity == Decimal("3")
        assert item.unit == "шт."
        assert item.unit_price == Decimal("7990")
        assert item.amount == Decimal("23970")
        assert item.feo_quantity == Decimal("3")
        assert item.feo_unit_price == Decimal("7990")
        assert item.feo_amount == Decimal("23970")
        if hasattr(item, "is_feo_breakdown"):
            assert item.is_feo_breakdown is True
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_item_name_equals_deepest_level_warns_and_keeps_both(db_session):
    """Строка 189 «Катер» (Ур.2 пуст, Ур.3=«Оборудование и снаряжение»,
    Ур.4=«Катер», «Плановая позиция»=«Катер», ФЭО=план=4 484 400): подраздел
    «Катер» получает budget=4 484 400, ОТДЕЛЬНАЯ обобщённая плановая позиция
    «Катер» тоже заводится (apply_collected_plan — лист без своих Ур.5 строк в
    этом импорте), но её feo_amount остаётся NULL (эта ветка не пишет ФЭО-
    комплект) — поэтому compute_budget_map НЕ прибавляет её сверх явного
    budget подраздела (см. test_subsidy_budget_single_source.py про эту же
    формулу). Человек обязан получить предупреждение `item_name_equals_category`."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl3="Оборудование и снаряжение", lvl4="Катер", item_name="Катер",
            feo_qty="1", feo_unit="шт.", feo_price="4484400", feo_sum="4484400",
            plan_qty="1", plan_unit="шт.", plan_price="4484400", plan_sum="4484400",
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        _matches = [w for w in result["warnings"] if w["kind"] == "item_name_equals_category"]
        assert len(_matches) == 1
        assert "Катер" in _matches[0]["message"]
        assert "4 484 400" in _matches[0]["message"] or "4484400" in _matches[0]["message"]

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Катер")
        assert leaf.budget == Decimal("4484400")

        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        assert items[0].name == "Катер"
        assert items[0].amount == Decimal("4484400")
        assert items[0].feo_amount is None, (
            "обобщённая позиция из apply_collected_plan не пишет feo_amount — "
            "иначе compute_budget_map задвоил бы budget подраздела"
        )
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_two_rows_same_name_as_category_stay_separate_items(db_session):
    """Боевой инцидент 12.10.2026, субсидия «ДНР 3», файл «ХО_ЛНР_ДНР_МАКЛЮК_
    Отправил.xlsx», лист «ДНРР», строки 151/152: ОБЕ называют себя как лист
    «Проезд, проживание, питание» (= имя Уровня 4), с РАЗНЫМИ суммами
    407 184,10 и 292 815,90. Старое правило «имя позиции = имя категории ⇒
    строка-итог» зануляло «Плановую позицию» у ОБЕИХ — вторая запись в
    collected_plan затирала первую, 407 184,10 терялись молча.

    Владелец (09.10.2026): «одинаковое название не даёт оснований смешивать
    категорию и плановую… плановая так и остаётся на плановой». Раз на этом
    пути ДВЕ строки заявляют позицию (а не одна, как в тесте про «Катер»
    выше) — это НЕ строка-итог ни у одной из них: обе уходят в обычный путь
    позиций Ур.5 и становятся группой дублей по имени (feo_import_duplicates.py),
    по умолчанию «оставить как есть» — суммы не теряются и не складываются."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(
                lvl3="Расходы закупка товаров, услуг, в том числе проезд, проживание и питание",
                lvl4="Проезд, проживание, питание",
                item_name="Проезд, проживание, питание",
                feo_sum="407184.10", plan_sum="407184.10",
            ),
            mk_row(
                lvl3="Расходы закупка товаров, услуг, в том числе проезд, проживание и питание",
                lvl4="Проезд, проживание, питание",
                item_name="Проезд, проживание, питание",
                feo_sum="292815.90", plan_sum="292815.90",
            ),
        ]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        assert not any(w["kind"] == "item_name_equals_category" for w in result["warnings"]), (
            "строка не одна на этом пути — это не самообъявленный итог категории"
        )
        assert not any(w["kind"] == "group_total_row" for w in result["warnings"])

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Проезд, проживание, питание")

        items = await _get_items(db_session, leaf.id)
        assert len(items) == 2, "обе строки обязаны остаться ОТДЕЛЬНЫМИ позициями, а не слиться в одну"
        amounts = sorted(it.amount for it in items)
        assert amounts == [Decimal("292815.90"), Decimal("407184.10")]
        assert sum(amounts) == Decimal("700000.00"), "сумма плана не должна потеряться"

        groups = [g for g in result.get("duplicate_groups", []) if g["name"] == "Проезд, проживание, питание"]
        assert len(groups) == 1, "две строки с одинаковым именем — группа дублей, человек решает сам"
        assert groups[0]["count"] == 2
        assert groups[0]["resolution"] == "keep"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
