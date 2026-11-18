"""Автономные тесты единства названий столбцов Excel, отступов ФЭО и обратной совместимости."""
from io import BytesIO
from types import SimpleNamespace

from openpyxl import Workbook, load_workbook

from app.services.excel_column_names import (
    COL_CONTRACTOR,
    COL_CONTRACTOR_INN,
    COL_CONTRACT_NUMBER,
    COL_FACT_QTY,
    COL_FACT_TOTAL,
    COL_FACT_UNIT_PRICE,
    COL_FEO_TOTAL,
    COL_FEO_UNIT_PRICE,
    COL_ITEM_NAME,
    COL_PLANNED_QTY,
    COL_PLANNED_TOTAL,
    COL_PLANNED_UNIT_PRICE,
    COL_PURCHASE_NUMBER,
    COL_UNIT,
    normalize_excel_header,
)
from app.services.feo_export_columns import FEO_EXPORT_COLUMNS, resolve_selected_keys
from app.services.feo_export_xlsx import (
    build_feo_roundtrip_template_workbook,
    render_feo_tree_sheet,
)
from app.services.feo_import_fact_summary import detect_fact_columns_by_header
from app.services.feo_roundtrip_import.parse import parse_roundtrip_workbook
from app.services.historical_fact_import.columns import (
    TEMPLATE_HEADER as FACT_TEMPLATE_HEADER,
    _map_columns_format,
)
from app.services.historical_fact_import.template_stages import _HEADER as FACT_STAGES_HEADER
from app.services.import_template_spec import _COL_SPEC as PURCHASE_IMPORT_SPEC
from app.services.plan_graph_export_columns import PLAN_GRAPH_COLUMNS
from app.services.plan_graph_export_xlsx import build_live_plan_graph_xlsx
from app.services.purchase_export_cells import ALL_EXPORT_COLUMNS as PURCHASE_EXPORT_COLUMNS
from app.services.purchase_import_parser_maps import _COLUMN_MAP


def _cat(cid: int, name: str, level: int, *, budget=None, parent_id=None):
    return SimpleNamespace(
        id=cid, name=name, level=level, budget=budget, parent_id=parent_id,
        code=f"0{cid}", appendix="1", is_active=True,
    )


def _item(iid: int, name: str, *, qty=2, unit_price=100.0, amount=200.0):
    return SimpleNamespace(
        id=iid, name=name, quantity=qty, unit="шт", unit_price=unit_price, amount=amount,
        feo_quantity=qty, feo_unit_price=unit_price, feo_amount=amount,
        is_active=True, item_type="Товары", notes="",
    )


def test_feo_export_tree_indentation_and_roundtrip():
    wb = Workbook()
    c1 = _cat(1, "Направление оснащения", 1)
    c2 = _cat(2, "Полевое снаряжение", 2, parent_id=1)
    c3 = _cat(3, "Палатки и укрытия", 3, parent_id=2)
    it = _item(101, "Палатка экспедиционная 4-местная")

    roots = [{"cat": c1, "children": [{"cat": c2, "children": [{"cat": c3, "children": []}]}]}]
    selected_keys = resolve_selected_keys(None)
    assert selected_keys[0] == "name"

    ws, _top, last_row = render_feo_tree_sheet(
        wb, "ФЭО", selected_keys, roots, {3: [it]}, {}, {},
        totals_label="Итого", include_row_ids=True,
    )
    assert ws.cell(row=3, column=1).value == COL_ITEM_NAME

    by_name = {}
    for r in range(4, last_row + 1):
        val = ws.cell(row=r, column=1).value
        if val:
            by_name[val.strip()] = r

    r1 = by_name["Направление оснащения"]
    r2 = by_name["Полевое снаряжение"]
    r3 = by_name["Палатки и укрытия"]
    ri = by_name["Палатка экспедиционная 4-местная"]

    assert (ws.cell(r1, 1).alignment.indent or 0) == 0
    assert (ws.cell(r2, 1).alignment.indent or 0) == 2
    assert (ws.cell(r3, 1).alignment.indent or 0) == 4
    assert (ws.cell(ri, 1).alignment.indent or 0) == 6
    assert ws.cell(ri, 1).alignment.wrap_text is True
    assert (ws.row_dimensions[ri].height or 0) >= 19.0
    assert ws.row_dimensions[r2].outline_level == 1
    assert ws.row_dimensions[r3].outline_level == 2
    assert ws.row_dimensions[ri].outline_level == 3

    buf = BytesIO()
    wb.save(buf)
    parsed = parse_roundtrip_workbook(buf.getvalue())
    assert parsed.errors == []
    assert [row.name for row in parsed.rows] == [
        "Направление оснащения",
        "Полевое снаряжение",
        "Палатки и укрытия",
        "Палатка экспедиционная 4-местная",
    ]


def test_feo_roundtrip_template_and_legacy_headers_parse():
    tpl_wb = build_feo_roundtrip_template_workbook()
    buf = BytesIO()
    tpl_wb.save(buf)
    parsed = parse_roundtrip_workbook(buf.getvalue())
    assert parsed.errors == []
    assert len(parsed.rows) >= 10

    # Старая выгрузка со старыми названиями колонок должна разбираться без ошибок
    legacy_wb = Workbook()
    ws = legacy_wb.active
    ws.append(["Итого"])
    ws.append(["Итого по фильтру"])
    ws.append([
        "Наименование товара", "Кол-во по ФЭО", "Ед. изм. (ОКЕИ)", "Цена за ед. по ФЭО (₽)",
        "Финансирование по ФЭО (₽)", "Плановое количество", "Плановая цена",
        "Плановая стоимость за объём", "Тип строки", "№ в системе",
    ])
    ws.append(["Раздел 1", None, None, None, 1000, None, None, None, "Категория", "c10"])
    ws.append(["  Позиция 1", 2, "шт", 500, 1000, 2, 500, 1000, "Позиция", "p20"])
    legacy_buf = BytesIO()
    legacy_wb.save(legacy_buf)
    legacy_parsed = parse_roundtrip_workbook(legacy_buf.getvalue())
    assert legacy_parsed.errors == []
    assert len(legacy_parsed.rows) == 2
    assert legacy_parsed.rows[1].plan_unit_price == 500
    assert legacy_parsed.rows[1].plan_amount == 1000


def test_canonical_column_names_unified_and_backward_compatible():
    purchase_tpl_headers = {s["header"] for s in PURCHASE_IMPORT_SPEC}
    assert {
        COL_ITEM_NAME, COL_UNIT, COL_PLANNED_QTY, COL_PLANNED_UNIT_PRICE, COL_PLANNED_TOTAL,
        COL_FACT_QTY, COL_FACT_UNIT_PRICE, COL_FACT_TOTAL, COL_CONTRACT_NUMBER, COL_CONTRACTOR, COL_CONTRACTOR_INN,
    } <= purchase_tpl_headers

    assert PURCHASE_EXPORT_COLUMNS["item_name"]["label"] == COL_ITEM_NAME
    assert PURCHASE_EXPORT_COLUMNS["unit"]["label"] == COL_UNIT
    assert PURCHASE_EXPORT_COLUMNS["planned_unit_price"]["label"] == COL_PLANNED_UNIT_PRICE
    assert PURCHASE_EXPORT_COLUMNS["planned_total_price"]["label"] == COL_PLANNED_TOTAL
    assert PURCHASE_EXPORT_COLUMNS["final_unit_price"]["label"] == COL_FACT_UNIT_PRICE
    assert PURCHASE_EXPORT_COLUMNS["final_total_amount"]["label"] == COL_FACT_TOTAL
    assert PURCHASE_EXPORT_COLUMNS["contract_number"]["label"] == COL_CONTRACT_NUMBER

    feo_labels = {k: lbl for k, lbl, *_ in FEO_EXPORT_COLUMNS}
    assert feo_labels["name"] == COL_ITEM_NAME
    assert feo_labels["feo_unit"] == COL_UNIT
    assert feo_labels["plan_qty"] == COL_PLANNED_QTY
    assert feo_labels["plan_unit_price"] == COL_PLANNED_UNIT_PRICE
    assert feo_labels["plan"] == COL_PLANNED_TOTAL
    assert feo_labels["fact_qty"] == COL_FACT_QTY
    assert feo_labels["fact_unit_price"] == COL_FACT_UNIT_PRICE
    assert feo_labels["fact_amount"] == COL_FACT_TOTAL
    assert feo_labels["feo_unit_price"] == COL_FEO_UNIT_PRICE
    assert feo_labels["feo"] == COL_FEO_TOTAL
    assert feo_labels["purchase_number"] == COL_PURCHASE_NUMBER

    pg_labels = {k: lbl for k, lbl, *_ in PLAN_GRAPH_COLUMNS}
    assert pg_labels["name"] == COL_ITEM_NAME
    assert pg_labels["unit"] == COL_UNIT
    assert pg_labels["qty"] == COL_PLANNED_QTY

    assert COL_ITEM_NAME in FACT_TEMPLATE_HEADER
    assert COL_PLANNED_UNIT_PRICE in FACT_TEMPLATE_HEADER
    assert COL_PLANNED_TOTAL in FACT_TEMPLATE_HEADER
    assert COL_ITEM_NAME in FACT_STAGES_HEADER
    assert COL_PLANNED_UNIT_PRICE in FACT_STAGES_HEADER
    assert COL_FACT_UNIT_PRICE in FACT_STAGES_HEADER

    # Парсеры принимают и новые канонические названия, и прежние алиасы
    for raw, expected_field in [
        ("Плановая цена за ед.", "plan_unit_price"),
        ("Цена за ед. (план)", "plan_unit_price"),
        ("Плановая сумма", "plan_total"),
        ("Сумма план", "plan_total"),
        ("Фактическая цена за ед.", "fact_unit_price"),
        ("Цена за ед. (факт)", "fact_unit_price"),
        ("Фактическая сумма", "fact_total"),
        ("Сумма факт", "fact_total"),
    ]:
        assert _COLUMN_MAP[normalize_excel_header(raw)] == expected_field

    mapped_new = {c["field"] for c in _map_columns_format(FACT_STAGES_HEADER) if c["field"]}
    assert {"plan_item_name", "plan_qty", "plan_price", "plan_amount", "fact_price", "fact_amount"} <= mapped_new

    fact_block = detect_fact_columns_by_header([
        "правильный статус", "фактическое количество", "фактическая цена за ед.",
        "фактическая сумма", "оплачено", "законтрактовано", "контрагент", "номер закупки",
    ])
    assert all(v is not None for v in fact_block.values())


def test_plan_graph_export_sets_indent_and_outline():
    c1 = _cat(1, "Направление", 1, budget=1000)
    c2 = _cat(2, "Тип", 2, parent_id=1)
    c3 = _cat(3, "Статья", 3, parent_id=2)
    it = _item(10, "Позиция А", qty=1, unit_price=500, amount=500)
    sub = SimpleNamespace(name="Субсидия", year=2026)
    data = {
        "cats": [c1, c2, c3],
        "items_by_cat": {3: [it]},
        "used_map": {10: 500.0},
        "contractor_map": {10: "ООО Тест"},
        "status_sums_map": {10: {"ordered": 500.0}},
        "cat_status_map": {},
        "cat_monthly_map": {},
        "cat_contractor_map": {},
        "purchased_by_item": {},
        "purchased_by_cat": {},
        "unlinked_purchases": [],
        "purchase_rows_by_id": {},
        "purchase_export_ctx": {},
        "contract_balance_by_purchase_id": {},
        "item_plan_map": {10: 500.0},
    }
    wb = build_live_plan_graph_xlsx(
        sub, "https://example.local", data, selected_columns=["level", "name", "plan_amount"]
    )
    ws = wb.active
    assert ws.sheet_properties.outlinePr.summaryBelow is False
    rows = {ws.cell(r, 2).value: r for r in range(4, ws.max_row + 1) if ws.cell(r, 2).value}
    assert (ws.cell(rows["Статья"], 2).alignment.indent or 0) == 4
    assert (ws.cell(rows["Позиция А"], 2).alignment.indent or 0) == 6
    assert ws.row_dimensions[rows["Позиция А"]].outline_level == 3
