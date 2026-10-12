"""Состав объединённой плановой позиции (владелец, 12.10.2026, план
merged-item-parts.md): загрузка плана «Объединить в одну» должна сохранять
СОСТАВ группы в FeoPlannedItem.parts — иначе «Gaz A22R35 Х920АЕ 180»
(352 400 = 317 400 + 20 000 + 10 000 + 5 000, 4 отдельные закупки) теряет
привязку «какая строка файла дала какой кусок суммы».

Использует тот же приём, что test_feo_import_duplicate_names.py (ПРАВИЛО №6 —
не дублировать `mk_row`/`_make_subsidy`/`_import` с dry_run/duplicate_
resolutions второй раз).

Известная особенность проекта: async-тесты этого файла гонять по одному:
`python -m pytest tests/test_feo_import_merged_parts.py::<имя> -x -q`."""
import json
from decimal import Decimal

import pytest

from tests.test_feo_import_duplicate_names import _import
from tests.test_feo_import_tree import _cleanup_subsidy, _get_categories, _get_items, _make_subsidy, mk_row


@pytest.mark.asyncio
async def test_merge_builds_parts_from_group_rows(db_session):
    """4 строки файла («Gaz…» 317 400/20 000/10 000/5 000) объединены в одну
    позицию — parts обязана нести 4 элемента, по одному на строку, с её
    собственной суммой (НЕ усреднённой), ключ = номер строки файла строкой."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        rows = [
            mk_row(lvl2="Транспорт", item_name="Gaz A22R35 Х920АЕ 180", plan_qty="1", plan_sum="317400"),
            mk_row(lvl2="Транспорт", item_name="Gaz A22R35 Х920АЕ 180", plan_qty="1", plan_sum="20000"),
            mk_row(lvl2="Транспорт", item_name="Gaz A22R35 Х920АЕ 180", plan_qty="1", plan_sum="10000"),
            mk_row(lvl2="Транспорт", item_name="Gaz A22R35 Х920АЕ 180", plan_qty="1", plan_sum="5000"),
        ]
        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        assert preview["errors"] == []
        group_key = preview["duplicate_groups"][0]["key"]

        result = await _import(db_session, subsidy_id, rows, duplicate_resolutions={group_key: "merge"})
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy_id)
        leaf = next(c for c in cats if c.name == "Транспорт")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        item = items[0]
        assert item.amount == Decimal("352400")

        parts = item.parts
        assert len(parts) == 4, parts
        assert {p["key"] for p in parts} == {"2", "3", "4", "5"}, "key = номер строки файла строкой"
        amounts = sorted(p["amount"] for p in parts)
        assert amounts == [5000.0, 10000.0, 20000.0, 317400.0]
        rows_in_parts = sorted(p["row"] for p in parts)
        assert rows_in_parts == [2, 3, 4, 5]
        # Типы — ТОЛЬКО JSON-совместимые (str/float/int), без Decimal.
        for p in parts:
            assert isinstance(p["amount"], float)
            assert isinstance(p["key"], str)
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


@pytest.mark.asyncio
async def test_non_merged_item_has_empty_parts(db_session):
    """Обычная (не объединённая) позиция — parts = [] (не отсутствие поля,
    не null) — фронт не должен рисовать раскрытие на части."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        rows = [mk_row(lvl2="Канцтовары", item_name="Карандаш", plan_sum="100")]
        result = await _import(db_session, subsidy_id, rows)
        assert result["errors"] == []
        cats = await _get_categories(db_session, subsidy_id)
        leaf = next(c for c in cats if c.name == "Канцтовары")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        assert items[0].parts == []
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


@pytest.mark.asyncio
async def test_repeated_import_keeps_same_part_keys_no_duplication(db_session):
    """Повторная загрузка ТОГО ЖЕ файла с тем же «Объединить» — ТЕ ЖЕ key
    (номера строк не меняются между прогонами одного файла), позиция
    обновляется (не дублируется), parts не растут вторым набором."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        rows = [
            mk_row(lvl2="Транспорт", item_name="Gaz A22R35 Х920АЕ 180", plan_qty="1", plan_sum="317400"),
            mk_row(lvl2="Транспорт", item_name="Gaz A22R35 Х920АЕ 180", plan_qty="1", plan_sum="20000"),
        ]
        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        group_key = preview["duplicate_groups"][0]["key"]

        result1 = await _import(db_session, subsidy_id, rows, duplicate_resolutions={group_key: "merge"})
        assert result1["errors"] == []
        cats = await _get_categories(db_session, subsidy_id)
        leaf = next(c for c in cats if c.name == "Транспорт")
        items1 = await _get_items(db_session, leaf.id)
        assert len(items1) == 1
        parts1 = items1[0].parts
        assert {p["key"] for p in parts1} == {"2", "3"}

        # Повторная загрузка — тот же файл, тот же group_key (стабилен, см.
        # feo_import_duplicates.group_key — текстовый ключ по именам, не id).
        result2 = await _import(db_session, subsidy_id, rows, duplicate_resolutions={group_key: "merge"})
        assert result2["errors"] == []
        items2 = await _get_items(db_session, leaf.id)
        assert len(items2) == 1, "позиция обновлена, не задвоена"
        assert items2[0].id == items1[0].id
        parts2 = items2[0].parts
        assert {p["key"] for p in parts2} == {"2", "3"}, "те же key между прогонами"
        assert len(parts2) == 2, "parts не растут вторым набором при повторной загрузке"
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)
