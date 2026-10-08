"""Тест листа «Реестр договоров» (владелец 08.10.2026…09.10.2026, 4 волны):
  волна 1 — рамочный договор с двумя заказами;
  волна 2 (прод ФАДМ 2026_2) — «Сумма» разнесена на уровень ДОГОВОРА/ЗАЯВКИ;
  волна 3 — числа вместо формул в строках данных, столбец «Уровень», строки
    «Позиция»;
  волна 4 (владелец 09.10.2026) — row outline (группировка, всё развёрнуто,
    summaryBelow=False); у разового договора С позициями «Сумма заявки»/
    «Поставлено»/«Оплачено» теперь в строках «Позиция», не в строке
    договора; itemless разовый — как раньше, в строке договора; «Вид
    договора»/«Тип договора» во всех строках; number_format верхних строк
    итогов.
Проверяется только РЕНДЕР (write_contracts_sheet) на уже собранных `groups` —
та же форма, что отдаёт gather_contracts_sheet_data
(plan_graph_export_contracts_data.py)."""
from app.services.plan_graph_export_contracts_sheet import (
    DATA_FIRST_ROW, HEADER_ROW, write_contracts_sheet,
)


def _item(name, unit, qty, unit_price, total, item_type=None):
    return {"name": name, "unit": unit, "qty": qty, "unit_price": unit_price, "total": total, "item_type": item_type}


def _framework_group():
    return {
        "head": {
            "purchase_number": 1093, "registry_number": "РЕЕ-2026-03048",
            "contract_number": "2026 СТО", "contract_date": "2026-01-10",
            "contractor": "ЦЕНТРАВТО", "contractor_inn": "7700000000",
            "subject": "Рамочный договор на СТО", "contract_sum": 600000.0, "ordered": 350000.0,
            "remaining": 250000.0, "delivered_total": 200000.0, "paid_total": 50000.0,
            "is_framework": True,
            "status": "Заказано", "category_path": "Направление / Тип / Статья",
            "purchase_id": 1093, "items": [],
            "contract_type_view": "Рамочный накопительный", "contract_kind": "Оказание услуг",
        },
        "orders": [
            {
                "order_number": "1", "purchase_number": 1098, "registry_number": "РЕЕ-2026-03053",
                "subject": "Заказ 1", "sum": 150000.0, "delivered": 150000.0, "paid": 50000.0,
                "status": "Поставлено", "pp_number": "ПП-1", "pp_date": "2026-02-01",
                "pp_amount": 50000.0, "category_path": "Направление / Тип / Статья", "purchase_id": 1098,
                "items": [
                    # Под заявкой рамочного — позиции НЕ несут order_sum/delivered/paid
                    # (деньги заявки уже в её собственной строке, владелец, волна 4).
                    _item("Замена масла", "усл.", 1.0, 50000.0, 50000.0),
                    _item("Запчасти", "шт.", 2.0, 50000.0, 100000.0),
                ],
                "item_kind": "Услуга", "planned_payment_month": "2026-02-01", "payment_month": "02.2026",
            },
            {
                "order_number": "2", "purchase_number": 1094, "registry_number": "РЕЕ-2026-03049",
                "subject": "Заказ 2", "sum": 200000.0, "delivered": 50000.0, "paid": 0.0,
                "status": "Заказано", "pp_number": "", "pp_date": "", "pp_amount": "",
                "category_path": "Направление / Тип / Статья", "purchase_id": 1094, "items": [],
                "item_kind": "Товар", "planned_payment_month": "", "payment_month": "",
            },
        ],
        "sort_key": 1093,
    }


def _single_group_with_items():
    """Разовый с позициями (владелец, волна 4): уровень ЗАЯВКИ ТОЛЬКО на
    строках «Позиция», строка договора — заявочные столбцы пустые."""
    return {
        "head": {
            "purchase_number": 2001, "registry_number": "РЕЕ-2026-05000",
            "contract_number": "ДОГ-2001", "contract_date": "2026-03-01",
            "contractor": "ООО Ромашка", "contractor_inn": "7711111111",
            "subject": "Разовая поставка", "contract_sum": 80000.0, "ordered": 80000.0,
            "remaining": 0.0, "delivered_total": 80000.0, "paid_total": 80000.0,
            "is_framework": False,
            "status": "Оплачено", "category_path": "Направление / Тип / Статья 2",
            "purchase_id": 2001,
            "single_sum": 80000.0, "single_delivered": 80000.0, "single_paid": 80000.0,
            "single_status": "Оплачено",
            "items": [
                {**_item("Товар А", "шт.", 3.0, 10000.0, 30000.0),
                 "order_sum": 30000.0, "order_delivered": 30000.0, "order_paid": 30000.0},
                {**_item("Товар Б", "шт.", 1.0, 50000.0, 50000.0),
                 "order_sum": 50000.0, "order_delivered": 50000.0, "order_paid": 50000.0},
            ],
            "item_kind": "Товар", "planned_payment_month": "2026-03-10", "payment_month": "03.2026",
            "contract_type_view": "Разовый", "contract_kind": "Поставка товаров",
        },
        "orders": [],
        "sort_key": 2001,
    }


def _single_group_itemless():
    """Разовый БЕЗ позиций (владелец, волна 4): уровень ЗАЯВКИ остаётся в
    строке договора — иначе потерялся бы."""
    return {
        "head": {
            "purchase_number": 3001, "registry_number": "РЕЕ-2026-06000",
            "contract_number": "ДОГ-3001", "contract_date": "2026-04-01",
            "contractor": "ООО Лютик", "contractor_inn": "7722222222",
            "subject": "Разовая услуга без позиций", "contract_sum": 40000.0, "ordered": 40000.0,
            "remaining": 0.0, "delivered_total": 40000.0, "paid_total": 40000.0,
            "is_framework": False,
            "status": "Оплачено", "category_path": "Направление / Тип / Статья 3",
            "purchase_id": 3001,
            "single_sum": 40000.0, "single_delivered": 40000.0, "single_paid": 40000.0,
            "single_status": "Оплачено",
            "items": [],
            "item_kind": "Услуга", "planned_payment_month": "2026-04-05", "payment_month": "04.2026",
            "contract_type_view": "Разовый", "contract_kind": "Оказание услуг",
        },
        "orders": [],
        "sort_key": 3001,
    }


def _build():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_contracts_sheet(wb, [_framework_group(), _single_group_with_items(), _single_group_itemless()])
    ws = wb["Реестр договоров"]
    headers = {cell.value: idx + 1 for idx, cell in enumerate(ws[HEADER_ROW])}
    return wb, ws, headers


def test_framework_contract_row_split_levels_no_double_count():
    wb, ws, headers = _build()

    def _val(row_idx, label):
        return ws.cell(row=row_idx, column=headers[label]).value

    head_row = DATA_FIRST_ROW        # 5
    order1_row = head_row + 1        # 6
    item1a_row = order1_row + 1      # 7
    item1b_row = order1_row + 2      # 8
    order2_row = order1_row + 3      # 9

    assert _val(head_row, "Уровень") == "Договор"
    assert _val(head_row, "№ закупки") == 1093
    assert _val(head_row, "Контрагент") == "ЦЕНТРАВТО"
    assert _val(head_row, "ИНН") == "7700000000"
    assert _val(head_row, "№ договора") == "2026 СТО"
    assert _val(head_row, "Вид договора") == "Рамочный накопительный"
    assert _val(head_row, "Тип договора") == "Оказание услуг"
    assert _val(head_row, "Сумма договора, ₽") == 600000.0
    assert _val(head_row, "Сумма заявок по договору, ₽") == 350000.0
    assert _val(head_row, "Осталось недозаказанных средств на договоре, ₽") == 250000.0
    assert _val(head_row, "Поставлено по договору, ₽") == 200000.0
    assert _val(head_row, "Оплачено по договору, ₽") == 50000.0
    assert _val(head_row, "Сумма заявки, ₽") == ""
    assert _val(head_row, "Статья ФЭО") == "Направление / Тип / Статья"
    for label in ("Сумма договора, ₽", "Сумма заявок по договору, ₽", "Осталось недозаказанных средств на договоре, ₽"):
        v = _val(head_row, label)
        assert not (isinstance(v, str) and v.startswith("="))

    assert _val(order1_row, "Уровень") == "Заявка"
    assert _val(order1_row, "№ заявки в договоре") == "1"
    assert _val(order1_row, "Сумма заявки, ₽") == 150000.0
    assert _val(order1_row, "Поставлено, ₽") == 150000.0
    assert _val(order1_row, "Оплачено, ₽") == 50000.0
    assert _val(order1_row, "Сумма договора, ₽") == ""
    assert _val(order1_row, "Контрагент") == "ЦЕНТРАВТО"
    assert _val(order1_row, "№ договора") == "2026 СТО"
    assert _val(order1_row, "Вид договора") == "Рамочный накопительный"
    assert _val(order1_row, "Тип договора") == "Оказание услуг"
    assert _val(order1_row, "Товар / услуга") == "Услуга"
    assert _val(order1_row, "План. месяц платежа") == "2026-02-01"

    # Позиции под заявкой рамочного — НЕ несут «Сумма заявки» (деньги уже в
    # строке заявки выше, владелец волна 4: только у разового).
    assert _val(item1a_row, "Уровень") == "Позиция"
    assert _val(item1a_row, "Сумма позиции, ₽") == 50000.0
    assert _val(item1a_row, "Сумма заявки, ₽") == ""
    assert _val(item1a_row, "Поставлено, ₽") == ""
    assert _val(item1a_row, "Вид договора") == "Рамочный накопительный"
    assert _val(item1a_row, "Тип договора") == "Оказание услуг"
    assert _val(item1b_row, "Сумма позиции, ₽") == 100000.0
    assert _val(item1a_row, "Сумма позиции, ₽") + _val(item1b_row, "Сумма позиции, ₽") == 150000.0  # == сумма заявки 1 (своя строка выше)

    assert _val(order2_row, "№ заявки в договоре") == "2"

    assert ws.auto_filter.ref is not None
    assert ws.freeze_panes == f"A{DATA_FIRST_ROW}"


def test_single_with_items_money_on_item_rows_not_head():
    wb, ws, headers = _build()

    def _val(row_idx, label):
        return ws.cell(row=row_idx, column=headers[label]).value

    # Порядок строк: head(5) + order1(6) + item1a(7) + item1b(8) + order2(9)
    # = 5 строк рамочного, затем разовый с позициями.
    single_row = DATA_FIRST_ROW + 5          # 10
    item_a_row = single_row + 1              # 11
    item_b_row = single_row + 2              # 12

    assert _val(single_row, "Уровень") == "Договор"
    assert _val(single_row, "№ закупки") == 2001
    assert _val(single_row, "Вид договора") == "Разовый"
    assert _val(single_row, "Тип договора") == "Поставка товаров"
    assert _val(single_row, "Сумма договора, ₽") == 80000.0
    assert _val(single_row, "Сумма заявок по договору, ₽") == 80000.0
    assert _val(single_row, "Поставлено по договору, ₽") == 80000.0
    assert _val(single_row, "Оплачено по договору, ₽") == 80000.0
    # ВЛАДЕЛЕЦ, волна 4: уровень ЗАЯВКИ у разового С ПОЗИЦИЯМИ — пуст в
    # строке договора, деньги на строках «Позиция».
    assert _val(single_row, "Сумма заявки, ₽") == ""
    assert _val(single_row, "Поставлено, ₽") == ""
    assert _val(single_row, "Оплачено, ₽") == ""

    assert _val(item_a_row, "Уровень") == "Позиция"
    assert _val(item_a_row, "Предмет / состав") == "Товар А"
    assert _val(item_a_row, "Сумма позиции, ₽") == 30000.0
    assert _val(item_a_row, "Сумма заявки, ₽") == 30000.0
    assert _val(item_a_row, "Поставлено, ₽") == 30000.0
    assert _val(item_a_row, "Оплачено, ₽") == 30000.0
    assert _val(item_a_row, "Вид договора") == "Разовый"
    assert _val(item_a_row, "Тип договора") == "Поставка товаров"

    assert _val(item_b_row, "Сумма позиции, ₽") == 50000.0
    assert _val(item_b_row, "Сумма заявки, ₽") == 50000.0

    # Σ по позициям разового == значениям строки договора (владелец, тест
    # на итог — замечание 2).
    assert _val(item_a_row, "Сумма позиции, ₽") + _val(item_b_row, "Сумма позиции, ₽") == _val(single_row, "Сумма договора, ₽")
    assert _val(item_a_row, "Сумма заявки, ₽") + _val(item_b_row, "Сумма заявки, ₽") == _val(single_row, "Сумма договора, ₽")
    assert _val(item_a_row, "Поставлено, ₽") + _val(item_b_row, "Поставлено, ₽") == _val(single_row, "Поставлено по договору, ₽")
    assert _val(item_a_row, "Оплачено, ₽") + _val(item_b_row, "Оплачено, ₽") == _val(single_row, "Оплачено по договору, ₽")


def test_single_itemless_keeps_order_level_on_head_row():
    """Владелец, волна 4: разовая закупка БЕЗ позиций — суммы уровня заявки
    остаются в строке договора (иначе потерялись бы)."""
    wb, ws, headers = _build()

    def _val(row_idx, label):
        return ws.cell(row=row_idx, column=headers[label]).value

    # head(5) + order1(6) + item1a(7) + item1b(8) + order2(9) = рамочный (5
    # строк), single_with_items head(10) + 2 позиции (11,12) = 3 строки,
    # итого 8 строк до itemless-разового.
    itemless_row = DATA_FIRST_ROW + 8        # 13

    assert _val(itemless_row, "Уровень") == "Договор"
    assert _val(itemless_row, "№ закупки") == 3001
    assert _val(itemless_row, "Вид договора") == "Разовый"
    assert _val(itemless_row, "Тип договора") == "Оказание услуг"
    assert _val(itemless_row, "Сумма заявки, ₽") == 40000.0
    assert _val(itemless_row, "Поставлено, ₽") == 40000.0
    assert _val(itemless_row, "Оплачено, ₽") == 40000.0
    assert _val(itemless_row, "Товар / услуга") == "Услуга"
    assert _val(itemless_row, "План. месяц платежа") == "2026-04-05"


def test_row_outline_levels_and_summary_above_expanded_by_default():
    """Владелец, замечание 1: группировка Excel — договор=0, заявка=1,
    позиция под заявкой=2 (под разовым=1); всё развёрнуто; summaryBelow
    False (строка-итог сверху)."""
    wb, ws, headers = _build()

    assert ws.sheet_properties.outlinePr.summaryBelow is False

    head_row = DATA_FIRST_ROW
    order1_row = head_row + 1
    item1a_row = order1_row + 1
    item1b_row = order1_row + 2
    order2_row = order1_row + 3
    single_row = DATA_FIRST_ROW + 5
    item_a_row = single_row + 1
    item_b_row = single_row + 2
    itemless_row = DATA_FIRST_ROW + 8

    assert ws.row_dimensions[head_row].outline_level == 0
    assert ws.row_dimensions[order1_row].outline_level == 1
    assert ws.row_dimensions[item1a_row].outline_level == 2
    assert ws.row_dimensions[item1b_row].outline_level == 2
    assert ws.row_dimensions[order2_row].outline_level == 1
    assert ws.row_dimensions[single_row].outline_level == 0
    assert ws.row_dimensions[item_a_row].outline_level == 1
    assert ws.row_dimensions[item_b_row].outline_level == 1
    assert ws.row_dimensions[itemless_row].outline_level == 0

    last_row = itemless_row
    for r in range(head_row, last_row + 1):
        assert ws.row_dimensions[r].hidden is False


def test_top_summary_rows_number_format_matches_data_columns():
    """Владелец, замечание 5: цифры строк 1-2 (SUM/SUBTOTAL) — тот же
    number_format, что у данных столбца."""
    wb, ws, headers = _build()

    sum_col = headers["Сумма заявки, ₽"]
    data_cell = ws.cell(row=DATA_FIRST_ROW + 1, column=sum_col)  # первая заявка
    assert data_cell.number_format == "#,##0.00"

    top1 = ws.cell(row=1, column=sum_col)
    top2 = ws.cell(row=2, column=sum_col)
    assert top1.value == f"=SUM({ws.cell(row=HEADER_ROW, column=sum_col).column_letter}{DATA_FIRST_ROW}:{ws.cell(row=HEADER_ROW, column=sum_col).column_letter}100000)"
    assert top1.number_format == "#,##0.00"
    assert top1.alignment.horizontal == "right"
    assert top2.value == f"=SUBTOTAL(109,{ws.cell(row=HEADER_ROW, column=sum_col).column_letter}{DATA_FIRST_ROW}:{ws.cell(row=HEADER_ROW, column=sum_col).column_letter}100000)"
    assert top2.number_format == "#,##0.00"
    assert top2.alignment.horizontal == "right"
    assert ws.cell(row=2, column=1).value == "Итого по фильтру"

    # QA 09.10.2026: «Цена за ед., ₽» — тот же number_format/alignment, что
    # денежные столбцы, но НЕ входит в верхние SUM/SUBTOTAL (строки 1-2 там
    # пустые для этого столбца — суммировать цену за единицу бессмысленно).
    price_col = headers["Цена за ед., ₽"]
    price_data_cell = ws.cell(row=DATA_FIRST_ROW + 2, column=price_col)  # item1a_row
    assert price_data_cell.number_format == "#,##0.00"
    assert price_data_cell.alignment.horizontal == "right"
    assert ws.cell(row=1, column=price_col).value in (None, "")
    assert ws.cell(row=2, column=price_col).value in (None, "")


def test_contract_and_order_columns_never_filled_in_same_row():
    """Инвариант без задваивания (волна 2, сохранить и после волны 4):
    договорные/заявочные денежные столбцы не пересекаются построчно — КРОМЕ
    itemless-разового (владелец, замечание 2): у него оба уровня — это
    ОДНА и та же закупка без позиций, уровню заявки больше негде быть, и
    SUM-инвариант всё равно не задваивает (контрактные/заявочные — разные
    столбцы, Σ по каждому столбцу считает свою величину один раз)."""
    wb, ws, headers = _build()
    contract_cols = [headers[l] for l in (
        "Сумма договора, ₽", "Сумма заявок по договору, ₽",
        "Осталось недозаказанных средств на договоре, ₽",
        "Поставлено по договору, ₽", "Оплачено по договору, ₽",
    )]
    order_cols = [headers[l] for l in ("Сумма заявки, ₽", "Поставлено, ₽", "Оплачено, ₽")]
    last_row = ws.max_row
    itemless_single_row = DATA_FIRST_ROW + 8  # см. test_single_itemless_keeps_order_level_on_head_row
    for r in range(DATA_FIRST_ROW, last_row + 1):
        if r == itemless_single_row:
            continue
        contract_filled = any(ws.cell(row=r, column=c).value not in ("", None) for c in contract_cols)
        order_filled = any(ws.cell(row=r, column=c).value not in ("", None) for c in order_cols)
        assert not (contract_filled and order_filled), f"row {r} fills both levels"


def test_empty_groups_still_creates_sheet():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_contracts_sheet(wb, [])
    assert "Реестр договоров" in wb.sheetnames
