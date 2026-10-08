"""Тест листа «Реестр договоров» (владелец 08.10.2026…09.10.2026, 3 волны):
  волна 1 — рамочный договор с двумя заказами: строка договора (сумма +
    формула остатка) и под ней заказы по № заявки; разовый — одна строка;
  волна 2 (прод ФАДМ 2026_2) — «Сумма» разнесена на уровень ДОГОВОРА (своя
    тройка столбцов) и уровень ЗАЯВКИ (своя тройка+ПП), у головы заявочные
    столбцы пусты — обычный SUM/SUBTOTAL по любому денежному столбцу не
    задваивает; строки 1-3 — подпись/«Итого всего»/«Итого по фильтру»,
    шапка — строка 4, данные — с 5-й;
  волна 3 (владелец 09.10.2026, «это всё должно быть в цифрах») — формулы
    в строках данных заменены на числа (кроме строк 1-2 итогов); столбец
    «Уровень» первым (Договор/Заявка/Позиция); «Поставлено по договору»/
    «Оплачено по договору» и переименованный «Остаток по договору» →
    «Осталось недозаказанных средств на договоре»; строки «Позиция» под
    разовым договором и под каждой заявкой рамочного; «Контрагент»/«ИНН»/
    «№ договора» заполнены во всех строках.
Проверяется только РЕНДЕР (write_contracts_sheet) на уже собранных `groups` —
та же форма, что отдаёт gather_contracts_sheet_data."""
from app.services.plan_graph_export_contracts_sheet import (
    DATA_FIRST_ROW, HEADER_ROW, write_contracts_sheet,
)


def _item(name, unit, qty, unit_price, total):
    return {"name": name, "unit": unit, "qty": qty, "unit_price": unit_price, "total": total}


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
        },
        "orders": [
            {
                "order_number": "1", "purchase_number": 1098, "registry_number": "РЕЕ-2026-03053",
                "subject": "Заказ 1", "sum": 150000.0, "delivered": 150000.0, "paid": 50000.0,
                "status": "Поставлено", "pp_number": "ПП-1", "pp_date": "2026-02-01",
                "pp_amount": 50000.0, "category_path": "Направление / Тип / Статья", "purchase_id": 1098,
                "items": [
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


def _single_group():
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
                _item("Товар А", "шт.", 3.0, 10000.0, 30000.0),
                _item("Товар Б", "шт.", 1.0, 50000.0, 50000.0),
            ],
            "item_kind": "Товар", "planned_payment_month": "2026-03-10", "payment_month": "03.2026",
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

    head_row = DATA_FIRST_ROW        # 5
    order1_row = head_row + 1        # 6
    item1a_row = order1_row + 1      # 7 (позиция заказа 1)
    item1b_row = order1_row + 2      # 8
    order2_row = order1_row + 3      # 9
    single_row = order2_row + 1      # 10
    item_single_a_row = single_row + 1   # 11
    item_single_b_row = single_row + 2   # 12

    # Строка договора: уровень ДОГОВОРА — ЧИСЛА (не формулы), уровень ЗАЯВКИ
    # (Сумма заявки/Поставлено/Оплачено) — ПУСТОЙ.
    assert _val(head_row, "Уровень") == "Договор"
    assert _val(head_row, "№ закупки") == 1093
    assert _val(head_row, "Контрагент") == "ЦЕНТРАВТО"
    assert _val(head_row, "ИНН") == "7700000000"
    assert _val(head_row, "№ договора") == "2026 СТО"
    assert _val(head_row, "Сумма договора, ₽") == 600000.0
    assert _val(head_row, "Сумма заявок по договору, ₽") == 350000.0
    assert _val(head_row, "Осталось недозаказанных средств на договоре, ₽") == 250000.0
    assert _val(head_row, "Поставлено по договору, ₽") == 200000.0
    assert _val(head_row, "Оплачено по договору, ₽") == 50000.0
    assert _val(head_row, "Сумма заявки, ₽") == ""
    assert _val(head_row, "Поставлено, ₽") == ""
    assert _val(head_row, "Оплачено, ₽") == ""
    assert _val(head_row, "Статья ФЭО") == "Направление / Тип / Статья"
    # Ни одна ячейка строки данных — не формула (владелец, волна 3).
    for label in ("Сумма договора, ₽", "Сумма заявок по договору, ₽", "Осталось недозаказанных средств на договоре, ₽"):
        v = _val(head_row, label)
        assert not (isinstance(v, str) and v.startswith("="))

    # Строка заявки: уровень ЗАЯВКИ заполнен, уровень ДОГОВОРА — пуст;
    # Контрагент/ИНН/№ договора — заполнены (владелец, часть 4).
    assert _val(order1_row, "Уровень") == "Заявка"
    assert _val(order1_row, "№ заявки в договоре") == "1"
    assert _val(order1_row, "Сумма заявки, ₽") == 150000.0
    assert _val(order1_row, "Поставлено, ₽") == 150000.0
    assert _val(order1_row, "Оплачено, ₽") == 50000.0
    assert _val(order1_row, "Сумма договора, ₽") == ""
    assert _val(order1_row, "Контрагент") == "ЦЕНТРАВТО"
    assert _val(order1_row, "ИНН") == "7700000000"
    assert _val(order1_row, "№ договора") == "2026 СТО"

    # Владелец 08.10.2026, замечания 1/2 — «Товар / услуга» и месяцы платежа
    # на строке ЗАЯВКИ; голова рамочного (head_row) их не несёт вовсе (это
    # заявки/позиции под ней, не её собственный вид/платёж).
    assert _val(order1_row, "Товар / услуга") == "Услуга"
    assert _val(order1_row, "План. месяц платежа") == "2026-02-01"
    assert _val(order1_row, "Факт. месяц платежа (по ПП)") == "02.2026"
    assert _val(head_row, "Товар / услуга") == ""
    assert _val(head_row, "План. месяц платежа") == ""

    # Строки «Позиция» под заявкой 1 — состав, Контрагент/ИНН/№ договора те же.
    assert _val(item1a_row, "Уровень") == "Позиция"
    assert _val(item1a_row, "Предмет / состав") == "Замена масла"
    assert _val(item1a_row, "Ед.") == "усл."
    assert _val(item1a_row, "Кол-во") == 1.0
    assert _val(item1a_row, "Цена за ед., ₽") == 50000.0
    assert _val(item1a_row, "Сумма позиции, ₽") == 50000.0
    assert _val(item1a_row, "Контрагент") == "ЦЕНТРАВТО"
    assert _val(item1a_row, "ИНН") == "7700000000"
    assert _val(item1a_row, "№ договора") == "2026 СТО"
    assert _val(item1a_row, "Сумма заявки, ₽") == ""  # не задваивает заявку
    # «Товар / услуга» строки «Позиция» — наследуется от родительской заявки
    # (владелец: «тот же столбец в строках Заявка и Позиция»); месяцы
    # платежа на «Позиции» не дублируются (владелец ограничил Заявкой).
    assert _val(item1a_row, "Товар / услуга") == "Услуга"
    assert _val(item1a_row, "План. месяц платежа") == ""
    assert _val(item1b_row, "Сумма позиции, ₽") == 100000.0
    # Σ «Сумма позиции» заявки 1 == «Сумма заявки» заявки 1.
    assert _val(item1a_row, "Сумма позиции, ₽") + _val(item1b_row, "Сумма позиции, ₽") == _val(order1_row, "Сумма заявки, ₽")

    assert _val(order2_row, "№ заявки в договоре") == "2"

    # Разовый договор — одна строка (оба уровня в ней), под ней — 2 строки
    # «Позиция», Σ «Сумма позиции» == «Сумма договора».
    assert _val(single_row, "Уровень") == "Договор"
    assert _val(single_row, "№ закупки") == 2001
    assert _val(single_row, "Сумма договора, ₽") == 80000.0
    assert _val(single_row, "Сумма заявок по договору, ₽") == 80000.0
    assert _val(single_row, "Осталось недозаказанных средств на договоре, ₽") == 0.0
    assert _val(single_row, "Поставлено по договору, ₽") == 80000.0
    assert _val(single_row, "Оплачено по договору, ₽") == 80000.0
    assert _val(single_row, "Сумма заявки, ₽") == 80000.0
    assert _val(single_row, "Поставлено, ₽") == 80000.0
    assert _val(single_row, "Оплачено, ₽") == 80000.0
    # Разовый договор — «Товар / услуга» и месяцы платежа в ТОЙ ЖЕ строке
    # (владелец: «и у разового договора»).
    assert _val(single_row, "Товар / услуга") == "Товар"
    assert _val(single_row, "План. месяц платежа") == "2026-03-10"
    assert _val(single_row, "Факт. месяц платежа (по ПП)") == "03.2026"

    assert _val(item_single_a_row, "Уровень") == "Позиция"
    assert _val(item_single_a_row, "Предмет / состав") == "Товар А"
    assert _val(item_single_a_row, "Сумма позиции, ₽") == 30000.0
    assert _val(item_single_b_row, "Сумма позиции, ₽") == 50000.0
    assert _val(item_single_a_row, "Контрагент") == "ООО Ромашка"
    assert _val(item_single_a_row, "№ договора") == "ДОГ-2001"
    assert _val(item_single_a_row, "Товар / услуга") == "Товар"
    assert (
        _val(item_single_a_row, "Сумма позиции, ₽") + _val(item_single_b_row, "Сумма позиции, ₽")
        == _val(single_row, "Сумма договора, ₽")
    )

    # Часть B: строка 1 — подпись + «Итого всего» (SUM), строка 2 — «Итого по
    # фильтру» (SUBTOTAL). Формулы остаются ТОЛЬКО тут.
    assert ws.cell(row=2, column=1).value == "Итого по фильтру"
    sum_col = headers["Сумма заявки, ₽"]
    assert ws.cell(row=1, column=sum_col).value == f"=SUM(O{DATA_FIRST_ROW}:O100000)"
    assert ws.cell(row=2, column=sum_col).value == f"=SUBTOTAL(109,O{DATA_FIRST_ROW}:O100000)"

    # Верхний SUM «Оплачено» (заявочный уровень) = Σ оплаченных заявок/разовых,
    # без строк «Позиция» (их денежный столбец — «Сумма позиции», другой).
    paid_col = headers["Оплачено, ₽"]
    assert ws.cell(row=1, column=paid_col).value == f"=SUM({ws.cell(row=HEADER_ROW, column=paid_col).column_letter}{DATA_FIRST_ROW}:{ws.cell(row=HEADER_ROW, column=paid_col).column_letter}100000)"

    assert ws.auto_filter.ref is not None
    assert ws.freeze_panes == f"A{DATA_FIRST_ROW}"


def test_empty_groups_still_creates_sheet():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_contracts_sheet(wb, [])
    assert "Реестр договоров" in wb.sheetnames
