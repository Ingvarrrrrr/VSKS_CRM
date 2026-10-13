"""clear_source_rows (app/services/feo_planned_item_clear_source_rows.py) —
«Убрать номера строк файла», владелец 12.10.2026, план
lazy-swimming-hollerith.md п.4г: обнуляет source_row всех позиций субсидии и
parts[].row частей, parts[].key НЕ трогает (закупки привязаны к частям по
key — feo_plan_part_purchases.py)."""
import pytest

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.services.feo_planned_item_clear_source_rows import clear_source_rows
from tests.test_feo_import_tree import _cleanup_subsidy, _make_subsidy


async def _make_leaf_category(db_session, subsidy_id):
    cat = FeoCategory(subsidy_id=subsidy_id, name="Ремонт ТС", level=5, parent_id=None)
    db_session.add(cat)
    await db_session.flush()
    return cat


@pytest.mark.asyncio
async def test_clear_source_rows_clears_items_and_part_rows_keeps_keys(db_session):
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        cat = await _make_leaf_category(db_session, subsidy_id)
        item_plain = FeoPlannedItem(
            feo_category_id=cat.id, name="Утюг", amount=1000, is_active=True, source_row=5,
        )
        item_merged = FeoPlannedItem(
            feo_category_id=cat.id, name="Gaz A22R35", amount=352400, is_active=True, source_row=19,
            parts=[
                {"key": "19", "row": 19, "qty": 1, "unit": "шт", "unit_price": 317400, "amount": 317400},
                {"key": "20", "row": 20, "qty": 1, "unit": "шт", "unit_price": 20000, "amount": 20000},
            ],
        )
        item_untouched = FeoPlannedItem(
            feo_category_id=cat.id, name="Ручная позиция", amount=500, is_active=True, source_row=None,
        )
        db_session.add_all([item_plain, item_merged, item_untouched])
        await db_session.flush()

        result = await clear_source_rows(db_session, subsidy_id)
        await db_session.flush()

        assert result == {"cleared_items": 2, "cleared_parts": 2}
        assert item_plain.source_row is None
        assert item_merged.source_row is None
        assert item_untouched.source_row is None  # уже было None — не считается "очищенной"

        assert [p["row"] for p in item_merged.parts] == [None, None]
        assert [p["key"] for p in item_merged.parts] == ["19", "20"]  # key НЕ трогается
        assert [p["amount"] for p in item_merged.parts] == [317400, 20000]  # остальные поля целы
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


@pytest.mark.asyncio
async def test_clear_source_rows_noop_when_already_clear(db_session):
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        cat = await _make_leaf_category(db_session, subsidy_id)
        item = FeoPlannedItem(feo_category_id=cat.id, name="Утюг", amount=1000, is_active=True)
        db_session.add(item)
        await db_session.flush()

        result = await clear_source_rows(db_session, subsidy_id)
        assert result == {"cleared_items": 0, "cleared_parts": 0}
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)
