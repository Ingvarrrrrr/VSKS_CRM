"""Автотесты на боевой инцидент 2026-09-15 (файл «Абхазия ЦЭМАК (1).xlsx»):
кол-во/ед./цена по ФЭО строки, когда в строке есть «Плановая позиция»,
принадлежат ЭТОЙ позиции, а не глубокому уровню категории.

Раньше (feo_import_apply.py, блок `_deepest_lv["feo_qty"]/feo_amt`) эти поля
безусловно уходили в самый глубокий заполненный уровень строки — единственный
их потребитель, фолбэк «план категории = feo_qty × feo_amt» (ветка «Старое
поведение источника данных»), срабатывал даже когда КАЖДАЯ строка категории на
самом деле несла свою позицию. Фантомный «план категории» из ПЕРВОЙ строки
затем сравнивался с суммой всех позиций категории и давал ложный
`plan_vs_items_mismatch` (боевой пример: категория «Альпинистское снаряжение»,
строки 2–26, план строки 4×970=3880 против суммы 25 позиций 780 000).

Использует те же макет строки (`mk_row`/`ROW_FIELDS`/`_IDX`) и хелперы
(`_make_subsidy`/`_cleanup_subsidy`/`_get_categories`/`_get_items`/`_import`),
что и `test_feo_import_tree.py` — импортированы оттуда напрямую (Правило №6,
не дублировать макет строки второй раз).

ВАЖНО (та же особенность, что в test_feo_import_tree.py): async-тесты в этом
файле падают с «different loop», если запускать 2+ штук в одном вызове
pytest. Гонять по одному:
`python -m pytest tests/test_feo_import_row_numbers_belong_to_item.py::<имя> -x -q`.
"""
from decimal import Decimal

import pytest

from tests.test_feo_import_tree import (
    _cleanup_subsidy,
    _get_categories,
    _get_items,
    _import,
    _make_subsidy,
    mk_row,
)


@pytest.mark.asyncio
async def test_item_row_feo_numbers_do_not_seed_phantom_category_plan(db_session):
    """Строка несёт и уровни (Ур.2/Ур.3), и «Плановую позицию», и кол-во/цену
    по ФЭО (плоские row-колонки, без отдельных «Количество»/«Цена» позиции и
    без плановых колонок) — эти кол-во/цена принадлежат ПОЗИЦИИ: категория не
    получает fallback-план, plan_vs_items_mismatch не возникает, а сама
    позиция создаётся с суммой feo_qty × feo_price."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Направление J9", lvl3="Категория J9",
            item_name="Позиция J9",
            feo_qty="4", feo_price="970",  # 3 880 — должно уйти позиции, не категории
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert not any(w["kind"] == "plan_vs_items_mismatch" for w in result["warnings"]), (
            f"категория не должна получать фантомный план: {result['warnings']}"
        )
        assert not any(w["kind"] == "group_plan_ignored" for w in result["warnings"])

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Категория J9")
        assert leaf.planned_quantity is None and leaf.planned_amount is None

        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        item = items[0]
        assert item.name == "Позиция J9"
        assert item.amount == Decimal("3880")
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_category_row_without_item_still_uses_feo_fallback(db_session):
    """Контроль: строка-категория БЕЗ «Плановой позиции» (файл ЦЕНТРПОИСК,
    строки-заголовки) — поведение фолбэка не меняется: feo_qty × feo_price
    по-прежнему становится планом самой категории (нет позиции, к которой
    можно было бы отнести эти числа)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Направление K9", lvl3="Категория K9",
            feo_qty="2", feo_price="400000",  # план категории = 800 000, фолбэк как раньше
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert not any(w["kind"] == "plan_vs_items_mismatch" for w in result["warnings"]), (
            "без второй позиции с другой суммой сравнивать не с чем"
        )

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Категория K9")

        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1, "лист без своих Ур.5-строк описывается позицией с именем категории"
        item = items[0]
        assert item.name == "Категория K9"
        assert item.quantity == Decimal("2")
        assert item.amount == Decimal("800000")
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
