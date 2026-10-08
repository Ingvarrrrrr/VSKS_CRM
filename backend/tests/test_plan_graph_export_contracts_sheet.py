"""Тест листа «Реестр договоров» (владелец 08.10.2026, 2 волны правок):
  волна 1 — рамочный договор с двумя заказами: строка договора (сумма +
    формула остатка) и под ней заказы по № заявки; разовый — одна строка;
  волна 2 (прод ФАДМ 2026_2) — «Сумма» разнесена на уровень ДОГОВОРА (своя
    тройка столбцов) и уровень ЗАЯВКИ (своя тройка+ПП), у головы заявочные
    столбцы пусты — обычный SUM/SUBTOTAL по любому денежному столбцу не
    задваивает; строки 1-3 — подпись/«Итого всего»/«Итого по фильтру»,
    шапка — строка 4, данные — с 5-й.
Проверяется только РЕНДЕР (write_contracts_sheet) на уже собранных `groups` —
та же форма, что отдаёт gather_contracts_sheet_data."""
from app.services.plan_graph_export_contracts_sheet import (
    DATA_FIRST_ROW, HEADER_ROW, write_contracts_sheet,
)


def _framework_group():
    return {
        "head": {
            "purchase_number": 1093, "registry_number": "РЕЕ-2026-03048",
            "contract_number": "2026 СТО", "contract_date": "2026-01-10",
            "contractor": "ЦЕНТРАВТО", "contractor_inn": "7700000000",
            "subject": "Рамочный договор на СТО", "contract_sum": 600000.0, "ordered": 0.0,
            "is_framework": True,
            "status": "Заказано", "category_path": "Направление / Тип / Статья",
            "purchase_id": 1093,
        },
        "orders": [
            {
                "order_number": "1", "purchase_number": 1098, "registry_number": "РЕЕ-2026-03053",
                "subject": "Заказ 1", "sum": 150000.0, "delivered": 150000.0, "paid": 50000.0,
                "status": "Поставлено", "pp_number": "ПП-1", "pp_date": "2026-02-01",
                "pp_amount": 50000.0, "category_path": "Направление / Тип / Статья", "purchase_id": 1098,
            },
            {
                "order_number": "2", "purchase_number": 1094, "registry_number": "РЕЕ-2026-03049",
                "subject": "Заказ 2", "sum": 200000.0, "delivered": 50000.0, "paid": 50000.0,
                "status": "Заказано", "pp_number": "", "pp_date": "", "pp_amount": "",
                "category_path": "Направление / Тип / Статья", "purchase_id": 1094,
            },
        ],
        "sort_key": 1093,
    }


def _single_group():
    return {
        "head": {
            "purchase_number": 2001, "registry_number": "РЕЕ-2026-05000",
            "contract_number": "ДОГ-2001", "contract_date": "2026-03-01",
            "contractor": "ООО Ромашка", "contractor_inn": "7711111111",
            "subject": "Разовая поставка", "contract_sum": 80000.0, "ordered": 80000.0,
            "is_framework": False,
            "status": "Оплачено", "category_path": "Направление / Тип / Статья 2",
            "purchase_id": 2001,
            "single_sum": 80000.0, "single_delivered": 80000.0, "single_paid": 80000.0,
            "single_status": "Оплачено",
        },
        "orders": [],
        "sort_key": 2001,
    }


def test_framework_contract_row_split_levels_no_double_count():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_contracts_sheet(wb, [_framework_group(), _single_group()])

    ws = wb["Реестр договоров"]
    headers = {cell.value: idx + 1 for idx, cell in enumerate(ws[HEADER_ROW])}

    def _val(row_idx, label):
        return ws.cell(row=row_idx, column=headers[label]).value

    head_row = DATA_FIRST_ROW       # 5
    order1_row = head_row + 1       # 6
    order2_row = head_row + 2       # 7
    single_row = head_row + 3       # 8

    # Строка договора: уровень ДОГОВОРА заполнен, уровень ЗАЯВКИ (Сумма
    # заявки/Поставлено/Оплачено) — ПУСТОЙ (владелец, волна 2).
    assert _val(head_row, "№ закупки") == 1093
    assert _val(head_row, "Сумма договора, ₽") == 600000.0
    assert _val(head_row, "Заказано по договору, ₽") == f"=SUM(L{order1_row}:L{order2_row})"
    assert _val(head_row, "Остаток по договору, ₽") == f"=I{head_row}-J{head_row}"
    assert _val(head_row, "Сумма заявки, ₽") == ""
    assert _val(head_row, "Поставлено, ₽") == ""
    assert _val(head_row, "Оплачено, ₽") == ""
    assert _val(head_row, "Статья ФЭО") == "Направление / Тип / Статья"

    # Строки заявок: уровень ЗАЯВКИ заполнен, уровень ДОГОВОРА — пуст.
    assert _val(order1_row, "№ заявки в договоре") == "1"
    assert _val(order1_row, "Сумма заявки, ₽") == 150000.0
    assert _val(order1_row, "Поставлено, ₽") == 150000.0
    assert _val(order1_row, "Оплачено, ₽") == 50000.0
    assert _val(order1_row, "Сумма договора, ₽") is None
    assert _val(order2_row, "№ заявки в договоре") == "2"

    # Разовый договор — одна строка, оба уровня заполнены в ней.
    assert _val(single_row, "№ закупки") == 2001
    assert _val(single_row, "Сумма договора, ₽") == 80000.0
    assert _val(single_row, "Заказано по договору, ₽") == 80000.0
    assert _val(single_row, "Сумма заявки, ₽") == 80000.0
    assert _val(single_row, "Поставлено, ₽") == 80000.0
    assert _val(single_row, "Оплачено, ₽") == 80000.0

    # Часть B: строка 1 — подпись + «Итого всего» (SUM), строка 2 — «Итого по
    # фильтру» (SUBTOTAL).
    assert ws.cell(row=2, column=1).value == "Итого по фильтру"
    sum_col = headers["Сумма заявки, ₽"]
    assert ws.cell(row=1, column=sum_col).value == f"=SUM(L{DATA_FIRST_ROW}:L100000)"
    assert ws.cell(row=2, column=sum_col).value == f"=SUBTOTAL(109,L{DATA_FIRST_ROW}:L100000)"

    assert ws.auto_filter.ref is not None
    assert ws.freeze_panes == f"A{DATA_FIRST_ROW}"


def test_empty_groups_still_creates_sheet():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_contracts_sheet(wb, [])
    assert "Реестр договоров" in wb.sheetnames
