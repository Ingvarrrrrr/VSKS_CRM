"""Юнит-тесты app.services.tz_items — группировка/слияние дублей строк ТЗ
(владелец, 21.09, corrections-21-09.md W3). Чистые функции без БД — duck-typing
объекты вместо PurchaseItem/WishItem (см. докстринг модуля: работает с обоими
через одинаковый набор полей)."""
from decimal import Decimal

from app.services.tz_items import build_tz_rows, find_duplicate_groups, group_key


class _Item:
    _seq = 0

    def __init__(self, item_name, unit="шт", product_id=None, quantity=None,
                 unit_price=None, total_price=None, item_type="товар",
                 feo_category_id=None):
        _Item._seq += 1
        self.id = _Item._seq
        self.item_name = item_name
        self.unit = unit
        self.product_id = product_id
        self.quantity = quantity
        self.unit_price = unit_price
        self.total_price = total_price
        self.item_type = item_type
        self.feo_category_id = feo_category_id


def test_group_key_by_name_ignores_punctuation_and_case():
    a = _Item("Огнетушитель ОП-5", unit="шт")
    b = _Item("огнетушитель, оп-5!", unit="шт")
    assert group_key(a) == group_key(b)


def test_group_key_by_product_id_overrides_name():
    a = _Item("Огнетушитель ОП-5", product_id=42)
    b = _Item("Совсем другое имя", product_id=42)
    assert group_key(a) == group_key(b)


def test_group_key_different_units_are_different_groups():
    a = _Item("Кабель", unit="м")
    b = _Item("Кабель", unit="шт")
    assert group_key(a) != group_key(b)


def test_find_duplicate_groups_requires_at_least_two():
    items = [_Item("Огнетушитель", quantity=2), _Item("Стул", quantity=1)]
    groups = find_duplicate_groups(items)
    assert groups == []


def test_find_duplicate_groups_by_name_across_feo_categories():
    a = _Item("Огнетушитель ОП-5", quantity=Decimal("2"), unit_price=Decimal("1000"),
              total_price=Decimal("2000"), feo_category_id=1)
    b = _Item("огнетушитель оп-5", quantity=Decimal("3"), unit_price=Decimal("1000"),
              total_price=Decimal("3000"), feo_category_id=2)
    groups = find_duplicate_groups([a, b])
    assert len(groups) == 1
    g = groups[0]
    assert len(g["items"]) == 2
    assert g["qty_sum"] == Decimal("5")
    assert g["total_sum"] == Decimal("5000")
    assert g["prices_differ"] is False
    assert set(g["feo_category_ids"]) == {1, 2}


def test_find_duplicate_groups_by_product_id_ignores_name():
    a = _Item("Название А", product_id=7, quantity=Decimal("1"))
    b = _Item("Совсем другое название", product_id=7, quantity=Decimal("2"))
    groups = find_duplicate_groups([a, b])
    assert len(groups) == 1
    assert groups[0]["qty_sum"] == Decimal("3")


def test_build_tz_rows_merge_sums_quantity_and_total():
    a = _Item("Огнетушитель", quantity=Decimal("2"), unit_price=Decimal("1000"), total_price=Decimal("2000"))
    b = _Item("огнетушитель", quantity=Decimal("3"), unit_price=Decimal("1000"), total_price=Decimal("3000"))
    key = group_key(a)
    built = build_tz_rows([a, b], {key: "merge"})
    assert len(built["rows"]) == 1
    row = built["rows"][0]
    assert row["quantity"] == Decimal("5")
    assert row["total_price"] == Decimal("5000")
    assert row["price_averaged"] is False
    assert row["unit_price"] == Decimal("1000")
    assert built["unresolved_keys"] == []


def test_build_tz_rows_merge_averages_price_when_prices_differ():
    a = _Item("Огнетушитель", quantity=Decimal("2"), unit_price=Decimal("1000"), total_price=Decimal("2000"))
    b = _Item("огнетушитель", quantity=Decimal("3"), unit_price=Decimal("900"), total_price=Decimal("2700"))
    key = group_key(a)
    built = build_tz_rows([a, b], {key: "merge"})
    row = built["rows"][0]
    assert row["quantity"] == Decimal("5")
    assert row["total_price"] == Decimal("4700")
    assert row["price_averaged"] is True
    assert row["unit_price"] == Decimal("4700") / Decimal("5")


def test_build_tz_rows_keep_leaves_rows_separate():
    a = _Item("Огнетушитель", quantity=Decimal("2"))
    b = _Item("огнетушитель", quantity=Decimal("3"))
    key = group_key(a)
    built = build_tz_rows([a, b], {key: "keep"})
    assert len(built["rows"]) == 2
    assert built["unresolved_keys"] == []


def test_build_tz_rows_without_decision_is_unresolved_and_kept_separate():
    """Без решения молчаливого слияния больше нет (владелец, W3) — строки
    остаются раздельными, но группа попадает в unresolved_keys."""
    a = _Item("Огнетушитель", quantity=Decimal("2"))
    b = _Item("огнетушитель", quantity=Decimal("3"))
    built = build_tz_rows([a, b], {})
    assert len(built["rows"]) == 2
    assert built["unresolved_keys"] == [group_key(a)]


def test_build_tz_rows_handles_null_quantity():
    a = _Item("Огнетушитель", quantity=None, total_price=None)
    b = _Item("огнетушитель", quantity=Decimal("3"), total_price=Decimal("300"))
    key = group_key(a)
    built = build_tz_rows([a, b], {key: "merge"})
    row = built["rows"][0]
    assert row["quantity"] == Decimal("3")  # NULL пропущен при суммировании, не превращён в 0
    assert row["total_price"] == Decimal("300")


def test_build_tz_rows_no_duplicates_passthrough():
    items = [_Item("Стул", quantity=Decimal("1")), _Item("Стол", quantity=Decimal("2"))]
    built = build_tz_rows(items, {})
    assert len(built["rows"]) == 2
    assert built["duplicate_groups"] == []
    assert built["unresolved_keys"] == []
