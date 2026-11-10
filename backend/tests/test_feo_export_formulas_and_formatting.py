"""test_feo_export_formulas_and_formatting.py — Автономные тесты для доработок выгрузки ФЭО в Excel:
1. Сохранение формул произведения количества на цену в строках позиций (plan, fact_amount, feo) и в запасных строках.
2. Условное форматирование ячеек «Да» / «Нет» (CellIsRule) и колонок факта (fact_qty, fact_unit_price, fact_amount).
3. Приоритет ячеечных правил перед строчными (gradual row rules).
4. Логика load_item_procurement_and_payments: исключение факта для несостоявшихся закупок (work_in_progress без договора)
   и включение факта для contracted / с договором.
5. Логика _is_purchase_done: исключение внутренних purchase_number и order_number.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from openpyxl import Workbook
from openpyxl.formatting.rule import Rule

from app.services.feo_export_columns import DEFAULT_KEYS, resolve_selected_keys, column_index
from app.services.feo_export_xlsx import (
    render_feo_tree_sheet,
    load_item_procurement_and_payments,
    HEADER_ROW,
    DATA_FIRST_ROW,
)
from app.services.plan_item_stage import _is_purchase_done


def _make_mock_item(id_, name, qty=5, unit_price=1000, amount=5000, feo_qty=5, feo_unit_price=1000, feo_amount=5000):
    return SimpleNamespace(
        id=id_,
        name=name,
        unit="шт",
        quantity=qty,
        unit_price=unit_price,
        amount=amount,
        feo_quantity=feo_qty,
        feo_unit_price=feo_unit_price,
        feo_amount=feo_amount,
        is_active=True,
        notes="Тест",
    )


def _make_mock_cat(id_, name, level=1, parent_id=None, budget=100000):
    return SimpleNamespace(
        id=id_,
        name=name,
        level=level,
        parent_id=parent_id,
        budget=budget,
        code="01",
        appendix="1",
        is_active=True,
    )


def test_is_purchase_done_logic():
    """Проверка, что внутренние номера (purchase_number, order_number) НЕ считаются
    проведением закупки, а contract_number, protocol_number и статусы — считаются."""
    # Несостоявшаяся / в подготовке закупка с внутренними номерами -> False
    assert not _is_purchase_done("work_in_progress", purchase_number="PURCH-001", order_number="ORD-100")
    assert not _is_purchase_done("plan_schedule", purchase_number=42, order_number="007")
    assert not _is_purchase_done(None, purchase_number="123")

    # С договором или протоколом -> True
    assert _is_purchase_done("work_in_progress", contract_number="ДОГ-2026/01")
    assert _is_purchase_done("plan_schedule", protocol_number="ПР-44")

    # Статусы проведения закупки -> True
    for st in ("contracted", "ordered", "delivered", "paid"):
        assert _is_purchase_done(st)
        assert _is_purchase_done(st, purchase_number="1")


def test_formulas_in_item_rows_and_spare_rows():
    """Проверка сохранения формул произведения количества на цену в строках позиций и запасных строках."""
    wb = Workbook()
    selected_keys = resolve_selected_keys(
        "name,plan_qty,plan_unit_price,plan,fact_qty,fact_unit_price,fact_amount,"
        "feo_qty,feo_unit_price,feo,active,row_type,row_id"
    )

    cat_root = _make_mock_cat(1, "Корневая категория", level=1)
    cat_sub = _make_mock_cat(2, "Подкатегория", level=2, parent_id=1)
    node_sub = {"cat": cat_sub, "children": []}
    node_root = {"cat": cat_root, "children": [node_sub]}

    # Позиция 1: есть количество и цена (и план, и факт, и фэо)
    item1 = _make_mock_item(101, "Ноутбук", qty=10, unit_price=50000, amount=500000, feo_qty=10, feo_unit_price=50000, feo_amount=500000)
    # Позиция 2: только сумма без количества и цены
    item2 = _make_mock_item(102, "Услуги связи", qty=None, unit_price=None, amount=30000, feo_qty=None, feo_unit_price=None, feo_amount=30000)

    items_by_cat = {
        cat_sub.id: [item1, item2],
    }
    procurement_map = {
        101: {
            "fact_qty": 10,
            "fact_unit_price": 48000,
            "fact_amount": 480000,
        },
        102: {
            "fact_amount": 30000,
        },
    }

    ws, top_rows, last_row = render_feo_tree_sheet(
        wb, "ФЭО", selected_keys, [node_root], items_by_cat,
        item_segments_map={}, cat_segments_map={},
        totals_label="Итого", procurement_map=procurement_map,
    )

    ci_plan = column_index(selected_keys, "plan")
    ci_plan_qty = column_index(selected_keys, "plan_qty")
    ci_plan_price = column_index(selected_keys, "plan_unit_price")
    ci_fact_amt = column_index(selected_keys, "fact_amount")
    ci_fact_qty = column_index(selected_keys, "fact_qty")
    ci_fact_price = column_index(selected_keys, "fact_unit_price")
    ci_feo = column_index(selected_keys, "feo")
    ci_feo_qty = column_index(selected_keys, "feo_qty")
    ci_feo_price = column_index(selected_keys, "feo_unit_price")
    ci_row_id = column_index(selected_keys, "row_id")

    col_pq = ws.cell(row=HEADER_ROW, column=ci_plan_qty).column_letter
    col_pp = ws.cell(row=HEADER_ROW, column=ci_plan_price).column_letter
    col_fq = ws.cell(row=HEADER_ROW, column=ci_fact_qty).column_letter
    col_fp = ws.cell(row=HEADER_ROW, column=ci_fact_price).column_letter
    col_feoq = ws.cell(row=HEADER_ROW, column=ci_feo_qty).column_letter
    col_feop = ws.cell(row=HEADER_ROW, column=ci_feo_price).column_letter

    # Строка 1: Итого, Строка 2: Итого по фильтру, Строка 3: Заголовки,
    # Строка 4: Корневая категория, Строка 5: Подкатегория,
    # Строка 6: item1, Строка 7: item2
    r_item1 = 6
    r_item2 = 7

    # 1. Проверяем формулы у item1
    cell_plan_1 = ws.cell(row=r_item1, column=ci_plan)
    assert cell_plan_1.value == f"={col_pq}{r_item1}*{col_pp}{r_item1}"

    cell_fact_1 = ws.cell(row=r_item1, column=ci_fact_amt)
    assert cell_fact_1.value == f"={col_fq}{r_item1}*{col_fp}{r_item1}"

    cell_feo_1 = ws.cell(row=r_item1, column=ci_feo)
    assert cell_feo_1.value == f"={col_feoq}{r_item1}*{col_feop}{r_item1}"

    # 2. Проверяем, что у item2 (без количества и цены) остаётся число, а не формула
    cell_plan_2 = ws.cell(row=r_item2, column=ci_plan)
    assert cell_plan_2.value == 30000.0
    cell_fact_2 = ws.cell(row=r_item2, column=ci_fact_amt)
    assert cell_fact_2.value == 30000.0

    # 3. Проверяем формулы в 50 запасных строках (spare rows)
    assert last_row == 7
    for spare_r in range(last_row + 1, last_row + 51):
        cell_plan_spare = ws.cell(row=spare_r, column=ci_plan)
        expected_spare_formula = f'=IF(AND(${col_pq}{spare_r}<>"",${col_pp}{spare_r}<>""),${col_pq}{spare_r}*${col_pp}{spare_r},"")'
        assert cell_plan_spare.value == expected_spare_formula
        assert ws.cell(row=spare_r, column=ci_row_id).value.startswith(f'=IF($')


def test_conditional_formatting_rules_and_priority():
    """Проверка наличия и приоритета правил условного форматирования:
    - ячейки «Да» / «Нет» (type == 'cellIs')
    - колонки факта (fact_qty, fact_unit_price, fact_amount)
    - ячеечные правила добавлены ДО строчных правил (gradual row rules)
    """
    wb = Workbook()
    selected_keys = resolve_selected_keys(
        "name,plan_qty,plan_unit_price,plan,fact_qty,fact_unit_price,fact_amount,"
        "active,is_in_plan,in_work,purchase_done,protocol_signed,contracted,ordered_flag,delivered,paid_marked,paid_confirmed,"
        "row_type,row_id"
    )

    cat = _make_mock_cat(1, "Категория")
    item = _make_mock_item(101, "Товар 1")
    node = {"cat": cat, "children": []}
    items_by_cat = {cat.id: [item]}

    ws, top_rows, last_row = render_feo_tree_sheet(
        wb, "Тест", selected_keys, [node], items_by_cat,
        item_segments_map={}, cat_segments_map={},
        totals_label="Итого",
    )

    cf_rules = list(ws.conditional_formatting)
    assert len(cf_rules) > 0

    # Собираем все добавленные правила
    all_rules_in_order = []
    cell_rules_yes_no = []
    fact_rules = []

    for cf in cf_rules:
        range_str = str(cf.sqref)
        for rule in cf.rules:
            all_rules_in_order.append((range_str, rule))
            if rule.type == "cellIs":
                cell_rules_yes_no.append((range_str, rule))
            elif rule.type == "expression":
                f_text = rule.formula[0] if rule.formula else ""
                if "Категория" in f_text and any(sym in f_text for sym in ("<>$", "<$", ">$")):
                    fact_rules.append((range_str, rule, f_text))

    # 1. Проверяем наличие правил CellIsRule для «Да» и «Нет»
    assert len(cell_rules_yes_no) >= 20  # 10 статусных колонок * 2 правила ("Да" и "Нет")
    yes_rules = [r for _, r in cell_rules_yes_no if r.formula == ['"Да"']]
    no_rules = [r for _, r in cell_rules_yes_no if r.formula == ['"Нет"']]
    assert len(yes_rules) >= 10
    assert len(no_rules) >= 10
    # Проверяем цвета «Да» (зелёный DCFCE7, 166534, bold) и «Нет» (красный FEE2E2, 991B1B)
    assert yes_rules[0].dxf.fill.fgColor.rgb == "00DCFCE7"
    assert yes_rules[0].dxf.font.color.rgb == "00166534"
    assert yes_rules[0].dxf.font.b is True
    assert no_rules[0].dxf.fill.fgColor.rgb == "00FEE2E2"
    assert no_rules[0].dxf.font.color.rgb == "00991B1B"

    # 2. Проверяем правила колонок факта: fact_qty, fact_unit_price, fact_amount
    ci_fq = column_index(selected_keys, "fact_qty")
    ci_fup = column_index(selected_keys, "fact_unit_price")
    ci_fa = column_index(selected_keys, "fact_amount")
    col_fq = ws.cell(row=HEADER_ROW, column=ci_fq).column_letter
    col_fup = ws.cell(row=HEADER_ROW, column=ci_fup).column_letter
    col_fa = ws.cell(row=HEADER_ROW, column=ci_fa).column_letter

    assert any(col_fq in r_str for r_str, _, _ in fact_rules), "fact_qty conditional formatting rule missing"
    assert any(col_fup in r_str for r_str, _, _ in fact_rules), "fact_unit_price conditional formatting rule missing"
    assert any(col_fa in r_str for r_str, _, _ in fact_rules), "fact_amount conditional formatting rule missing"

    # Проверяем точные формулы отклонений факта
    fq_rules = [r for r_str, r, _ in fact_rules if col_fq in r_str]
    assert len(fq_rules) == 1
    assert "<>" in fq_rules[0].formula[0]

    fup_rules = [r for r_str, r, _ in fact_rules if col_fup in r_str]
    assert len(fup_rules) == 2
    fup_formulas = [r.formula[0] for r in fup_rules]
    assert any(">" in f for f in fup_formulas)
    assert any("<" in f for f in fup_formulas)

    fa_rules = [r for r_str, r, _ in fact_rules if col_fa in r_str]
    assert len(fa_rules) == 2
    fa_formulas = [r.formula[0] for r in fa_rules]
    assert any(">" in f for f in fa_formulas)
    assert any("<" in f for f in fa_formulas)

    # 3. Приоритет: правила для ячеек ("Да"/"Нет" и факта) должны идти ДО строчных правил
    first_row_rule_idx = next(i for i, (r_str, _) in enumerate(all_rules_in_order) if r_str.startswith(f"A{DATA_FIRST_ROW}:"))
    last_cell_rule_idx = max(i for i, (r_str, r) in enumerate(all_rules_in_order) if r.type == "cellIs")
    assert last_cell_rule_idx < first_row_rule_idx, "CellIsRule должен добавляться ДО строчных правил!"


def test_template_workbook_generation():
    """Проверка генерации шаблона выгрузки ФЭО build_feo_roundtrip_template_workbook."""
    from app.services.feo_export_xlsx import build_feo_roundtrip_template_workbook
    wb = build_feo_roundtrip_template_workbook()
    assert "Шаблон" in wb.sheetnames
    assert "Как заполнять" in wb.sheetnames
    assert "_meta" in wb.sheetnames
    ws = wb["Шаблон"]
    assert ws.cell(row=HEADER_ROW, column=1).value is not None


@pytest.mark.asyncio
async def test_load_item_procurement_filtering_work_in_progress_vs_contracted():
    """Проверка исправления бага:
    - Закупка work_in_progress без договора НЕ должна заполнять fact_amount, fact_qty, fact_unit_price!
    - Закупка contracted (или с contract_num) ДОЛЖНА заполнять fact_amount, fact_qty, fact_unit_price!
    """
    db_mock = AsyncMock()

    # Сценарий 1: Закупка со статусом 'work_in_progress' без договора и без итоговой цены
    row_wip = SimpleNamespace(
        feo_planned_item_id=1,
        pi_qty=10,
        pi_unit_price=318.0,  # черновая предварительная цена
        pi_final_unit_price=None,
        pi_total_price=3180.0,
        pi_final_total=None,
        pi_c_name="ООО Лампа",
        pi_c_inn="7700000001",
        p_id=50,
        purchase_number="42",
        p_order_number="ORD-1",
        registry_number="REG-1",
        p_protocol_num=None,
        contract_id=None,
        p_contract_num=None,
        p_contract_price=None,
        p_final_amt=None,
        p_pay_doc=None,
        p_pay_date=None,
        p_pay_amt=None,
        p_status="work_in_progress",
        contractor_id=None,
        c_name=None,
        c_inn=None,
        contract_num=None,
        contract_max_amt=None,
    )

    mock_pi_wip = MagicMock()
    mock_pi_wip.all.return_value = [row_wip]
    mock_pay_wip = MagicMock()
    mock_pay_wip.all.return_value = []
    db_mock.execute.side_effect = [mock_pi_wip, mock_pay_wip]

    res_wip = await load_item_procurement_and_payments(db_mock, [1])

    b_wip = res_wip[1]
    # Факт НЕ должен быть заполнен для work_in_progress!
    assert b_wip["fact_amount"] == "", "fact_amount для work_in_progress без договора должен быть пустым!"
    assert b_wip["fact_qty"] == "", "fact_qty для work_in_progress без договора должен быть пустым!"
    assert b_wip["fact_unit_price"] == "", "fact_unit_price для work_in_progress без договора должен быть пустым!"
    # Заказ/заявка при этом заполняется
    assert b_wip["order_amount"] == 3180.0

    # Сценарий 2: Закупка со статусом 'contracted' и договором
    row_contracted = SimpleNamespace(
        feo_planned_item_id=2,
        pi_qty=5,
        pi_unit_price=200.0,
        pi_final_unit_price=190.0,
        pi_total_price=1000.0,
        pi_final_total=950.0,
        pi_c_name="ООО Поставщик",
        pi_c_inn="7700000002",
        p_id=51,
        purchase_number="43",
        p_order_number="ORD-2",
        registry_number="REG-2",
        p_protocol_num="ПР-01",
        contract_id=10,
        p_contract_num="ДОГ-55",
        p_contract_price=950.0,
        p_final_amt=950.0,
        p_pay_doc=None,
        p_pay_date=None,
        p_pay_amt=None,
        p_status="contracted",
        contractor_id=1,
        c_name="ООО Поставщик",
        c_inn="7700000002",
        contract_num="ДОГ-55",
        contract_max_amt=950.0,
    )

    mock_pi_contracted = MagicMock()
    mock_pi_contracted.all.return_value = [row_contracted]
    mock_c_tot = MagicMock()
    mock_c_tot.all.return_value = [(10, 950.0)]
    mock_pay_contracted = MagicMock()
    mock_pay_contracted.all.return_value = []
    db_mock.execute.side_effect = [mock_pi_contracted, mock_c_tot, mock_pay_contracted]

    res_contracted = await load_item_procurement_and_payments(db_mock, [2])

    b_contracted = res_contracted[2]
    # Факт ДОЛЖЕН быть заполнен для contracted!
    assert b_contracted["fact_amount"] == 950.0
    assert b_contracted["fact_qty"] == 5.0
    assert b_contracted["fact_unit_price"] == 190.0
    assert b_contracted["contract_number"] == "ДОГ-55"
