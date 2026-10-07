"""Группировка строк импорта факта в закупки: поставщик+«№ Закупки» →
поставщик → листовая категория ФЭО; decisions.groups переопределяет."""
from app.services.historical_fact_import import grouping as grouping_mod
from app.services.historical_fact_import import statuses as statuses_mod


def _item(row_num, supplier=None, purchase_no=None, path=None, status_raw="В работе",
          fact_amount=1000, paid=None, contracted=None, category_id=None, skip=False):
    row = {
        "row": row_num, "name": f"Позиция {row_num}", "path": path or [],
        "fact": {"qty": 1, "price": fact_amount, "amount": fact_amount},
        "plan": {"qty": 1, "price": fact_amount, "amount": fact_amount},
        "paid": paid, "contracted": contracted, "supplier": supplier, "purchase_no": purchase_no,
        "skip": skip,
    }
    match = {"state": "found" if category_id is None else "found", "planned_item_id": 1,
             "candidates": [{"id": 1, "name": row["name"], "path": path or [], "amount": fact_amount,
                              "category_id": category_id}]}
    status_info = statuses_mod.resolve_status(status_raw)
    return {"row": row, "match": match, "status_info": status_info}


def test_group_by_supplier_and_purchase_no():
    rows = [_item(1, supplier="ООО Ромашка", purchase_no="42"), _item(2, supplier="ООО Ромашка", purchase_no="42")]
    groups = grouping_mod.build_groups(rows)
    assert len(groups) == 1
    assert set(groups[0]["rows"]) == {1, 2}


def test_group_by_supplier_only_without_purchase_no():
    rows = [_item(1, supplier="ООО Ромашка"), _item(2, supplier="ооо «ромашка»")]
    groups = grouping_mod.build_groups(rows)
    assert len(groups) == 1  # нормализация имени поставщика схлопывает разное написание


def test_group_by_category_when_no_supplier():
    rows = [_item(1, category_id=10), _item(2, category_id=10), _item(3, category_id=20)]
    groups = grouping_mod.build_groups(rows)
    assert len(groups) == 2
    sizes = sorted(len(g["rows"]) for g in groups)
    assert sizes == [1, 2]


def test_explicit_group_override():
    rows = [_item(1, supplier="А"), _item(2, supplier="Б"), _item(3, supplier="В")]
    decisions = {"groups": [{"rows": [1, 2]}]}
    groups = grouping_mod.build_groups(rows, decisions)
    group_with_both = [g for g in groups if set(g["rows"]) == {1, 2}]
    assert group_with_both, groups


def test_mixed_statuses_warn_and_take_highest_rank():
    rows = [_item(1, supplier="А", status_raw="В работе"), _item(2, supplier="А", status_raw="Оплачено", paid=1000)]
    groups = grouping_mod.build_groups(rows)
    assert len(groups) == 1
    assert groups[0]["status"] == "paid"
    assert groups[0]["warnings"]
    # Задание 07.10.2026 (п.5): подписи по-русски (STATUS_LABELS), не коды
    # ("work_in_progress", "paid") — owner: «смешаны статусы (delivered,
    # ordered)» было непонятно без расшифровки.
    warning = groups[0]["warnings"][0]
    assert "Ведётся работа" in warning
    assert "Оплачено" in warning
    assert "work_in_progress" not in warning
    codes_part = warning.split("(")[1].split(")")[0]
    assert "paid" not in codes_part


def test_mixed_statuses_ignore_skipped_rows():
    """Статус группы и «смешаны статусы» считаются ТОЛЬКО по активным
    (не пропущенным) строкам — пропущенная строка с другим статусом не
    должна красить статус всей группы (чек-лист, п.5)."""
    rows = [
        _item(1, supplier="А", status_raw="В работе"),
        _item(2, supplier="А", status_raw="Оплачено", paid=1000, skip=True),
    ]
    groups = grouping_mod.build_groups(rows)
    assert len(groups) == 1
    g = groups[0]
    assert g["status"] == "work_in_progress"
    assert not g["warnings"]
    assert g["active_rows"] == [1]
    assert g["all_skipped"] is False


def test_group_all_skipped_flagged():
    """Карточка, где пропущены ВСЕ строки группы, помечается all_skipped —
    фронт прячет такие карточки (StepGroups.vue)."""
    rows = [_item(1, supplier="А", status_raw="В работе", skip=True)]
    groups = grouping_mod.build_groups(rows)
    assert len(groups) == 1
    assert groups[0]["all_skipped"] is True
    assert groups[0]["active_rows"] == []
