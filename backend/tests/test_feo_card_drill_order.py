# -*- coding: utf-8 -*-
"""test_feo_card_drill_order.py — порядок строк окна «Запланировано» (card_drill_rows,
card="planned") внутри ОДНОЙ категории ОБЯЗАН идти по единому ключу
app.services.feo_planned_item_order (ручная перестановка sort_order, затем строка
файла загрузки source_row, затем id — ПРАВИЛО №6, не вторая сортировка).

Боевая находка (29.10.2026): владелец загружает план из Excel, строки внутри
категории в окне «Запланировано» шли НЕ в порядке файла — _classify_items не
сортировала выборку, а card="planned" ветка собирала строки по (категория, kind)
блоками, разбивая категорию по типам товар/услуга/...

Переиспользует фабрики test_feo_plan_tree_scenarios.py (ПРАВИЛО №6, не вторые
фабрики)."""
from decimal import Decimal

import pytest

from app.services.feo_card_drill import card_drill_rows
from app.services.feo_planned_item_order import planned_item_sort_key
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


@pytest.mark.asyncio
async def test_planned_card_orders_by_source_row_not_creation_order(db_session, test_org):
    """Три позиции одной категории созданы в порядке id=A,B,C со source_row
    34, 36, 35 (загрузка файла не совпадает с порядком INSERT — массовая
    загрузка плана не гарантирует порядок строк) — окно обязано вернуть их
    34, 35, 36 (порядок файла), а не порядок создания."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    cat = await _make_category(db_session, subsidy.id, name="Статья")

    it_a = await _make_planned_item(db_session, cat.id, "Строка 34", 1, 1000)
    it_a.item_type = "товар"
    it_b = await _make_planned_item(db_session, cat.id, "Строка 36", 1, 2000)
    it_b.item_type = "товар"
    it_c = await _make_planned_item(db_session, cat.id, "Строка 35", 1, 3000)
    it_c.item_type = "товар"
    it_a.source_row = 34
    it_b.source_row = 36
    it_c.source_row = 35
    await db_session.commit()

    result = await card_drill_rows(db_session, subsidy.id, "planned", "all")
    assert result["reason"] is None
    names = [r["name"] for r in result["rows"]]
    assert names == ["Строка 34", "Строка 35", "Строка 36"]


@pytest.mark.asyncio
async def test_planned_card_manual_sort_order_wins_over_source_row(db_session, test_org):
    """sort_order (перестановка стрелками) обязан выигрывать у source_row —
    позиция со sort_order=0 идёт первой, даже если её source_row больше, чем
    у остальных (без sort_order)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    cat = await _make_category(db_session, subsidy.id, name="Статья")

    it_first = await _make_planned_item(db_session, cat.id, "Строка 50 (переставлена первой)", 1, 1000)
    it_first.item_type = "товар"
    it_second = await _make_planned_item(db_session, cat.id, "Строка 10", 1, 2000)
    it_second.item_type = "товар"
    it_first.source_row = 50
    it_second.source_row = 10
    it_first.sort_order = 0
    await db_session.commit()

    result = await card_drill_rows(db_session, subsidy.id, "planned", "all")
    names = [r["name"] for r in result["rows"]]
    assert names == ["Строка 50 (переставлена первой)", "Строка 10"]


@pytest.mark.asyncio
async def test_planned_card_manual_item_without_source_row_goes_last(db_session, test_org):
    """Позиция, заведённая в GALA вручную (source_row=NULL, sort_order=NULL),
    идёт ПОСЛЕ позиций из загрузки файла (у которых source_row задан), а не
    перемешивается с ними по id."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    cat = await _make_category(db_session, subsidy.id, name="Статья")

    # Создаём ручную позицию ПЕРВОЙ (меньший id), чтобы порядок по id дал бы
    # неверный результат, если бы сортировка не учитывала source_row.
    it_manual = await _make_planned_item(db_session, cat.id, "Добавлена вручную", 1, 500)
    it_manual.item_type = "товар"
    it_file = await _make_planned_item(db_session, cat.id, "Строка файла 5", 1, 1500)
    it_file.item_type = "товар"
    it_file.source_row = 5
    await db_session.commit()

    result = await card_drill_rows(db_session, subsidy.id, "planned", "all")
    names = [r["name"] for r in result["rows"]]
    assert names == ["Строка файла 5", "Добавлена вручную"]


@pytest.mark.asyncio
async def test_planned_card_mixed_kinds_keep_source_row_order_without_split(db_session, test_org):
    """Категория с ЧЕРЕДУЮЩИМИСЯ товарами и услугами (по source_row) — окно
    обязано вернуть их в порядке файла, НЕ разбивая на блок «все товары»,
    затем блок «все услуги» (боевой дефект: card="planned" ветка раньше
    итерировала for cid in nodes: for k in kinds, что всегда разбивало
    категорию по типам)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    cat = await _make_category(db_session, subsidy.id, name="Статья смешанная")

    it1 = await _make_planned_item(db_session, cat.id, "Товар строка 1", 1, 1000)
    it1.item_type = "товар"
    it2 = await _make_planned_item(db_session, cat.id, "Услуга строка 2", 1, 2000)
    it2.item_type = "услуга"
    it3 = await _make_planned_item(db_session, cat.id, "Товар строка 3", 1, 3000)
    it3.item_type = "товар"
    it1.source_row = 1
    it2.source_row = 2
    it3.source_row = 3
    await db_session.commit()

    result = await card_drill_rows(db_session, subsidy.id, "planned", "all")
    names = [r["name"] for r in result["rows"]]
    assert names == ["Товар строка 1", "Услуга строка 2", "Товар строка 3"]


def test_planned_item_sort_key_semantics():
    """Юнит-тест ключа в памяти: sort_order < source_row < id, None — последним
    на каждом уровне (та же семантика, что NULLS LAST в planned_item_order_by)."""
    # sort_order задан — выигрывает у source_row/id независимо от их значений.
    assert planned_item_sort_key(0, 999, 1) < planned_item_sort_key(None, 1, 2)
    assert planned_item_sort_key(1, None, 100) < planned_item_sort_key(2, None, 1)

    # Оба sort_order=None — решает source_row.
    assert planned_item_sort_key(None, 5, 100) < planned_item_sort_key(None, 10, 1)

    # sort_order и source_row оба None — решает id.
    assert planned_item_sort_key(None, None, 1) < planned_item_sort_key(None, None, 2)

    # source_row=None идёт ПОСЛЕ любого заданного source_row (при равном sort_order=None).
    assert planned_item_sort_key(None, 1, 999) < planned_item_sort_key(None, None, 1)

    # sort_order=None идёт ПОСЛЕ любого заданного sort_order.
    assert planned_item_sort_key(5, None, 999) < planned_item_sort_key(None, 0, 1)

    keys = [
        planned_item_sort_key(None, 36, 10),
        planned_item_sort_key(None, 34, 8),
        planned_item_sort_key(None, 35, 9),
        planned_item_sort_key(None, None, 1),
    ]
    ordered = sorted(range(len(keys)), key=lambda i: keys[i])
    assert ordered == [1, 2, 0, 3]
