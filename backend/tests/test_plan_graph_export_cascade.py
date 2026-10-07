"""app.services.plan_graph_export_xlsx — Задачи B/C/D экспорта плана-графика
(владелец 07.10.2026): каскад сумм по стадиям накопительный, отменённые
закупки не считаются, выбор столбцов, лист «Сводная» — формулы в D/G/I и
ИТОГО. Строится через СИНТЕТИЧЕСКИЙ `data`-словарь (та же форма, что отдаёт
gather_live_plan_graph_data) — без БД, проверяется только рендер книги."""
from types import SimpleNamespace

import pytest

from app.services.plan_graph_export_columns import resolve_selected_keys
from app.services.plan_graph_export_xlsx import build_live_plan_graph_xlsx, cascade_by_stage


def _make_sub():
    return SimpleNamespace(name="Тестовая субсидия", year=2026)


def _make_cat(id_, level, parent_id=None, name="Статья", code=None, budget=None):
    return SimpleNamespace(id=id_, level=level, parent_id=parent_id, name=name, code=code, budget=budget)


def _make_item(id_, feo_category_id, name="Позиция", unit="шт", quantity=2, amount=1000):
    return SimpleNamespace(id=id_, feo_category_id=feo_category_id, name=name, unit=unit, quantity=quantity, amount=amount)


def _base_data():
    cat1 = _make_cat(1, 1, None, name="Направление", code="01")
    cat2 = _make_cat(2, 2, 1, name="Тип расходов")
    cat3 = _make_cat(3, 3, 2, name="Статья ФЭО")
    item = _make_item(10, 3)

    return {
        "cats": [cat1, cat2, cat3],
        "item_ids": [10],
        "cat_ids": [1, 2, 3],
        "items_by_cat": {3: [item]},
        "used_map": {10: 1000.0},
        "contractor_map": {10: "ООО Ромашка"},
        "status_sums_map": {10: {"paid": 1000.0}},
        "purchased_by_item": {10: [{
            "name": "Купленное", "unit": "шт", "qty": 2, "unit_price": 500.0,
            "total": 1000.0, "contractor": "ООО Ромашка", "raw_status": "paid",
            "status": "Оплачено", "purchase_id": 55, "act_number": "A-1",
        }]},
        "cat_status_map": {},
        "cat_monthly_map": {},
        "cat_contractor_map": {},
        "purchased_by_cat": {},
        "unlinked_purchases": [{
            "name": "Без категории (отменена)", "unit": "шт", "qty": 1, "unit_price": 500.0,
            "total": 500.0, "contractor": "X", "raw_status": "cancelled",
            "status": "Отменено", "purchase_id": 77, "act_number": "",
            "is_monthly": False, "monthly_count": None, "monthly_amount": 0.0,
        }],
    }


def test_cascade_by_stage_is_cumulative_for_paid():
    planned, contract, ordered, delivered, paid = cascade_by_stage("paid", 1000.0)
    assert (planned, contract, ordered, delivered, paid) == (1000.0, 1000.0, 1000.0, 1000.0, 1000.0)


def test_cascade_by_stage_partial_stage_ordered():
    planned, contract, ordered, delivered, paid = cascade_by_stage("ordered", 500.0)
    assert (planned, contract, ordered) == (500.0, 500.0, 500.0)
    assert (delivered, paid) == (0.0, 0.0)


def test_cascade_by_stage_cancelled_is_all_zero():
    assert cascade_by_stage("cancelled", 999.0) == (0.0, 0.0, 0.0, 0.0, 0.0)


def test_build_live_plan_graph_xlsx_item_row_cumulative_and_cancelled_excluded():
    wb = build_live_plan_graph_xlsx(_make_sub(), "http://example.test", _base_data())
    ws = wb["План закупок"]

    headers = {cell.value: idx + 1 for idx, cell in enumerate(ws[2])}
    rows = list(ws.iter_rows(min_row=3, values_only=False))
    item_row = next(r for r in rows if r[headers["Наименование"] - 1].value == "Позиция")

    def _val(row, label):
        return row[headers[label] - 1].value

    # Оплаченная позиция — накопительно во всех 5 столбцах.
    assert _val(item_row, "Запланировано, ₽") == 1000.0
    assert _val(item_row, "Договор, ₽") == 1000.0
    assert _val(item_row, "Заказано, ₽") == 1000.0
    assert _val(item_row, "Поставлено, ₽") == 1000.0
    assert _val(item_row, "Оплачено, ₽") == 1000.0
    assert _val(item_row, "Фактически (итого), ₽") == 1000.0

    # Отменённая закупка (секция «без категории») — все денежные столбцы 0,
    # не "" (видна, но не считается).
    cancelled_row = next(
        r for r in rows if "Без категории (отменена)" in str(r[headers["Наименование"] - 1].value or "")
    )
    assert _val(cancelled_row, "Запланировано, ₽") == 0.0
    assert _val(cancelled_row, "Фактически (итого), ₽") == 0.0


def test_column_selection_limits_headers_and_keeps_name():
    selected = resolve_selected_keys("paid,status")
    assert "name" in selected  # всегда присутствует
    assert selected.index("paid") < selected.index("status")  # фиксированный порядок PLAN_GRAPH_COLUMNS

    wb = build_live_plan_graph_xlsx(
        _make_sub(), "http://example.test", _base_data(), selected_columns=selected,
    )
    ws = wb["План закупок"]
    header_values = [c.value for c in ws[2] if c.value]
    assert header_values == ["Наименование", "Оплачено, ₽", "Статус"]


def test_resolve_selected_keys_empty_returns_default_only():
    """Владелец 07.10.2026: группа «Договор и оплата» — не в наборе по
    умолчанию; пустой ?columns= больше не означает «все столбцы»."""
    from app.services.plan_graph_export_columns import ALL_KEYS, DEFAULT_KEYS
    assert resolve_selected_keys(None) == list(DEFAULT_KEYS)
    assert resolve_selected_keys("") == list(DEFAULT_KEYS)
    assert set(DEFAULT_KEYS) < set(ALL_KEYS)  # новая группа существует, но не default


def test_columns_catalog_marks_default_flag():
    from app.services.plan_graph_export_columns import columns_catalog
    catalog = {c["key"]: c for c in columns_catalog()}
    assert catalog["name"]["default"] is True
    assert catalog["contract_number"]["default"] is False
    assert catalog["payment_doc_number"]["default"] is False
    assert catalog["contract_number"]["group"] == "Договор и оплата"


def test_new_contract_payment_columns_appear_only_when_selected():
    """Новый столбец («№ договора») отсутствует в выгрузке по умолчанию и
    появляется только если его явно выбрали через ?columns=."""
    data = _base_data()
    purchase = SimpleNamespace(
        id=55, purchase_number="55", order_number="", registry_number="РЕЕ-55",
        status="paid", subsidy_id=None, feo_category_id=None,
        item_name="", item_type="", unit="", planned_quantity=None,
        subject="", country_origin="", planned_unit_price=None, planned_total_price=None,
        total_nmck=None, contract_price=None, price_increase=None,
        purchase_method=None, purchase_basis=None, purchase_contract_type=None,
        framework_seq=None, contract_number="ДОГ-55/2026", contract_date=None,
        execution_term=None, execution_term_changed=None, delivery_date=None,
        contractor_id=None, reimbursement_user_id=None, service_note_by=None,
        responsible_person="", acceptance_doc_number="A-1", acceptance_docs=None,
        payment_doc_number="ПП-100", payment_doc_date=None, payment_amount=1000.0,
        payment_federal=None, delivery_payment_amount=None,
        vat_applicable=False, vat_rate=None, vat_exemption_article=None, vat_mode=None,
        etp_url=None, region="", delivery_region="", delivery_location="", delivery_address="",
        final_unit_price=None, final_total_amount=None, contract_end_date=None,
        submission_deadline=None, commitment_quarter=None, planned_payment_month=None,
        stage_label=None, substatus=None,
    )
    data["purchase_rows_by_id"] = {55: purchase}
    data["purchase_export_ctx"] = {
        "contractors": {}, "contractor_inns": {}, "subsidies": {}, "feo_categories": {},
        "payment_purposes": {55: "За услуги"}, "ru_map": {}, "sn_map": {}, "economy": {},
    }

    # По умолчанию (без явного выбора столбцов) — новой колонки нет вовсе.
    wb_default = build_live_plan_graph_xlsx(_make_sub(), "http://example.test", data)
    ws_default = wb_default["План закупок"]
    headers_default = [c.value for c in ws_default[2] if c.value]
    assert "№ договора" not in headers_default
    assert "ПП: №" not in headers_default

    # Явно выбрали — колонка появляется, в под-строке оплаченной закупки
    # заполнена значением с самой закупки, в строке плановой позиции — пусто.
    selected = resolve_selected_keys("name,paid,contract_number,payment_doc_number,payment_purpose")
    wb = build_live_plan_graph_xlsx(
        _make_sub(), "http://example.test", data, selected_columns=selected,
    )
    ws = wb["План закупок"]
    headers = {cell.value: idx + 1 for idx, cell in enumerate(ws[2])}
    assert "№ договора" in headers
    assert "ПП: №" in headers

    rows = list(ws.iter_rows(min_row=3, values_only=False))

    def _val(row, label):
        return row[headers[label] - 1].value

    item_row = next(r for r in rows if _val(r, "Наименование") == "Позиция")
    assert _val(item_row, "№ договора") == ""
    assert _val(item_row, "ПП: №") == ""

    sub_row = next(
        r for r in rows if "Купленное" in str(_val(r, "Наименование") or "")
    )
    assert _val(sub_row, "№ договора") == "ДОГ-55/2026"
    assert _val(sub_row, "ПП: №") == "ПП-100"
    assert _val(sub_row, "Назначение платежа") == "За услуги"


def test_summary_sheet_has_formulas_for_computed_columns_and_total():
    summary_by_kind = {
        "goods": {
            "feo": 100.0, "plan": 90.0, "committed": 40.0, "monthly": 10.0,
            "likely": 20.0, "nice": 20.0, "paid": 15.0, "delivered_unpaid": 5.0,
        },
        "services": {
            "feo": 0.0, "plan": 0.0, "committed": 0.0, "monthly": 0.0,
            "likely": 0.0, "nice": 0.0, "paid": 0.0, "delivered_unpaid": 0.0,
        },
        "payroll": {k: 0.0 for k in ("feo", "plan", "committed", "monthly", "likely", "nice", "paid", "delivered_unpaid")},
        "unspecified": {k: 0.0 for k in ("feo", "plan", "committed", "monthly", "likely", "nice", "paid", "delivered_unpaid")},
    }
    wb = build_live_plan_graph_xlsx(
        _make_sub(), "http://example.test", _base_data(), summary_by_kind=summary_by_kind,
    )
    assert "Сводная" in wb.sheetnames
    sm = wb["Сводная"]

    # Строка 5 — «Товары» (goods всегда показан), строка 6 — «Услуги».
    goods_row = 5
    assert sm.cell(row=goods_row, column=1).value == "Товары"
    assert sm.cell(row=goods_row, column=4).value == f"=C{goods_row}-H{goods_row}"
    assert sm.cell(row=goods_row, column=7).value == f"=D{goods_row}-E{goods_row}-F{goods_row}"
    assert sm.cell(row=goods_row, column=9).value == f"=J{goods_row}+K{goods_row}"

    services_row = 6
    assert sm.cell(row=services_row, column=1).value == "Услуги"

    # «ФОТ»/«Без типа» все нули — строки не рисуются.
    row_labels = [sm.cell(row=r, column=1).value for r in range(5, sm.max_row + 1)]
    assert "ФОТ" not in row_labels
    assert "Без типа" not in row_labels

    total_row = services_row + 1
    assert sm.cell(row=total_row, column=1).value == "ИТОГО"
    assert sm.cell(row=total_row, column=2).value == f"=SUM(B5:B{services_row})"


def test_no_summary_sheet_when_summary_by_kind_is_none():
    wb = build_live_plan_graph_xlsx(_make_sub(), "http://example.test", _base_data(), summary_by_kind=None)
    assert "Сводная" not in wb.sheetnames
