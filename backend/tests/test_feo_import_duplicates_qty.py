"""Регрессия бага владельца (22.09, скриншот предпросмотра импорта ФЭО):
группа дублей «Спасательный конец Александрова в чехле» (строки 269/270),
у ОБЕИХ строк количество в файле не задано (пустая ячейка) и сумма 0,00 —
предпросмотр предлагал «Объединить в одну (сумма 0,00 ₽, кол-во 2, цена
0,00 ₽ за ед.)». Причина: `_combine_rows`/`_describe_group` в
`app/services/feo_import_duplicates.py` подставляли 1 за каждую строку без
количества (`r["qty"] if r["qty"] is not None else ONE`) — оба числа
(кол-во 2, цена 0,00) были выдуманы, реального количества в файле нет.

Правило теперь (Правило №6 — обе функции зовут общую `_sum_qty`):
  - ни у одной строки группы количество не задано → merged qty = None
    (не 0 и не подстановка единицы), цена за единицу = None;
  - количество известно только у ЧАСТИ строк → merged qty = сумма
    известных, но цена за единицу ВСЁ РАВНО None (числитель верный, но
    знаменатель занижен — недостающее количество не 0, показывать цену,
    посчитанную на заведомо неполном количестве, нельзя);
  - количество известно у ВСЕХ строк группы → merged qty = сумма всех,
    цена = сумма amount / сумма qty (старое поведение для полностью
    заполненных строк не меняется, см.
    test_feo_import_duplicate_names.py::test_merge_resolution_combines_sum_and_quantity).

Сумма (`amount`) всегда точная сумма amount всех строк, независимо от того,
известно ли количество — деньги не зависят от количества.

ВАЖНО (известная особенность проекта, см. соседний test_feo_import_duplicate_names.py):
async-тесты в этом файле падают с «different loop», если запускать 2+ штук в
одном вызове pytest. Гонять по одному:
`python -m pytest tests/test_feo_import_duplicates_qty.py::<имя> -x -q`.
"""
import json
from decimal import Decimal

import pytest

from app.routers.feo_categories import _do_feo_import
from tests.test_feo_import_tree import (
    _IDX,
    _cleanup_subsidy,
    _get_categories,
    _get_items,
    _make_subsidy,
    mk_row,
)


async def _import(db_session, subsidy_id, rows, dry_run=False, duplicate_resolutions=None):
    """Копия `_import` из test_feo_import_duplicate_names.py (Правило №6 —
    не заводить третью реализацию того же вызова `_do_feo_import` с
    dry_run/duplicate_resolutions; берём её же по образцу, а не импортируем
    напрямую, т.к. модуль-сосед не экспортирует её как публичный хелпер)."""
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
        duplicate_resolutions=json.dumps(duplicate_resolutions) if duplicate_resolutions else "",
        db=db_session,
    )


@pytest.mark.asyncio
async def test_merge_without_any_qty_leaves_qty_and_price_unset(db_session):
    """Обе строки группы без количества (баг владельца, строки 269/270) —
    merged qty = None (не 2, как раньше через ONE), price = None (не 0,00),
    сумма = точная сумма amount двух строк."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        # plan_sum намеренно НЕ ноль (0 в этом импорте — отдельное значение
        # «плана по сути нет», см. `_item_has_plan_numbers` в
        # feo_import_apply.py, не связано с багом количества) — здесь
        # проверяется именно количество: ни у одной строки оно не задано.
        rows = [
            mk_row(lvl2="Склад", item_name="Спасательный конец Александрова в чехле", plan_sum="1500"),
            mk_row(lvl2="Склад", item_name="Спасательный конец Александрова в чехле", plan_sum="2500"),
        ]

        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        assert preview["errors"] == []
        group = preview["duplicate_groups"][0]
        assert group["merged_preview"] == {
            "qty": None, "unit": None, "price": None, "amount": 4000.0,
        }, "количество не задано ни у одной строки — merged qty и price обязаны быть None, а не 2 и 0,00"

        result = await _import(
            db_session, subsidy_id, rows,
            duplicate_resolutions={group["key"]: "merge"},
        )
        assert result["errors"] == []
        merge_warn = [w for w in result["warnings"] if w["kind"] == "duplicate_group_merged"]
        assert len(merge_warn) == 1
        assert "количество не задано" in merge_warn[0]["message"], merge_warn[0]["message"]

        cats = await _get_categories(db_session, subsidy_id)
        leaf = next(c for c in cats if c.name == "Склад")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        item = items[0]
        assert item.quantity is None, "количество не должно превратиться в выдуманную 1+1=2"
        assert item.amount == Decimal("4000")
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


@pytest.mark.asyncio
async def test_merge_partially_known_qty_sums_known_but_price_stays_unset(db_session):
    """Одна строка с количеством 3, вторая — без количества: merged qty =
    3 (сумма ИЗВЕСТНЫХ количеств), но цена за единицу всё равно None — 3
    посчитано не на полном количестве группы, показывать цену на заведомо
    заниженном знаменателе нельзя."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        rows = [
            mk_row(lvl2="Склад", item_name="Канат", plan_qty="3", plan_sum="3000"),
            mk_row(lvl2="Склад", item_name="Канат", plan_sum="1000"),
        ]

        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        assert preview["errors"] == []
        group = preview["duplicate_groups"][0]
        assert group["merged_preview"] == {
            "qty": 3.0, "unit": None, "price": None, "amount": 4000.0,
        }
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


@pytest.mark.asyncio
async def test_merge_all_qty_known_computes_price_as_before(db_session):
    """Обе строки с известным количеством (2 и 3) — старое поведение не
    трогаем: merged qty = 5, цена = сумма amount / 5."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        rows = [
            mk_row(lvl2="Склад", item_name="Трос", plan_qty="2", plan_sum="2000"),
            mk_row(lvl2="Склад", item_name="Трос", plan_qty="3", plan_sum="3000"),
        ]

        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        assert preview["errors"] == []
        group = preview["duplicate_groups"][0]
        assert group["merged_preview"] == {
            "qty": 5.0, "unit": None, "price": 1000.0, "amount": 5000.0,
        }
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)
