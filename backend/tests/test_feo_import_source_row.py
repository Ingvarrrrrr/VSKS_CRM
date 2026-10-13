"""source_row — номер строки файла загрузки плана (правка 12.10.2026, план
lazy-swimming-hollerith.md п.4г): «строка N файла» вместо нумерации позиции в
FeoLevel5Panel.vue. Пишет ТОЛЬКО _upsert_one (feo_import_duplicates.py),
читается через GET /feo-categories/plan-positions (feo_plan_reads_tree.py) и
FeoPlannedItemOut (schemas/feo.py)."""
from decimal import Decimal

import pytest

from app.routers.feo_categories import _do_feo_import
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


@pytest.mark.asyncio
async def test_source_row_set_on_first_load(db_session):
    """Строка файла (Excel-строка 2 и 3 — заголовок строка 1) — позиция
    получает source_row = её собственный номер строки."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        await _import(db_session, subsidy_id, [
            mk_row(lvl2="Кухня", item_name="Утюг", plan_sum="1000"),
            mk_row(lvl2="Ванная", item_name="Фен", plan_sum="2000"),
        ])
        cats = await _get_categories(db_session, subsidy_id)
        by_name = {c.name: c for c in cats}
        utyug = (await _get_items(db_session, by_name["Кухня"].id))[0]
        fen = (await _get_items(db_session, by_name["Ванная"].id))[0]
        assert utyug.source_row == 2
        assert fen.source_row == 3
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


@pytest.mark.asyncio
async def test_source_row_updates_on_reload_with_new_row_number(db_session):
    """Повторная загрузка того же файла — если позиция теперь на другой
    строке файла, source_row обновляется (ПРАВИЛО №6 — тот же путь _upsert_one,
    что обновляет quantity/amount)."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        await _import(db_session, subsidy_id, [
            mk_row(lvl2="Кухня", item_name="Утюг", plan_sum="1000"),
        ])
        await _import(db_session, subsidy_id, [
            mk_row(lvl2="Прочее", item_name="Заглушка", plan_sum="1"),
            mk_row(lvl2="Кухня", item_name="Утюг", plan_sum="1500"),
        ])
        cats = await _get_categories(db_session, subsidy_id)
        kitchen = next(c for c in cats if c.name == "Кухня")
        utyug = (await _get_items(db_session, kitchen.id))[0]
        assert utyug.source_row == 3
        assert utyug.amount == Decimal("1500")
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)
