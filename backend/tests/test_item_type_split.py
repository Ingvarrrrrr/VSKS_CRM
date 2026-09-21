"""Тесты для app/services/item_type_split.py (план ancient-prancing-music.md,
раздел A) — единственный источник правила «тип позиции → товары/услуги»."""
from decimal import Decimal
from types import SimpleNamespace

from app.services.item_type_split import (
    KIND_GOODS,
    KIND_SERVICES,
    KIND_UNSPECIFIED,
    TypeShares,
    kind_of,
    purchase_type_shares,
    split_amount_by_shares,
    sum_by_kind,
)


def _item(item_type, total_price):
    return SimpleNamespace(item_type=item_type, total_price=total_price)


class TestKindOf:
    def test_tovar(self):
        assert kind_of("товар") == KIND_GOODS

    def test_usluga_case_insensitive(self):
        assert kind_of("Услуга") == KIND_SERVICES

    def test_rabota_with_whitespace(self):
        assert kind_of("  работа  ") == KIND_SERVICES

    def test_empty_string(self):
        assert kind_of("") == KIND_UNSPECIFIED

    def test_none(self):
        assert kind_of(None) == KIND_UNSPECIFIED

    def test_unrecognized_value(self):
        assert kind_of("мусор") == KIND_UNSPECIFIED


class TestPurchaseTypeShares:
    def test_ordinary_purchase(self):
        items = [_item("товар", Decimal("300")), _item("услуга", Decimal("700"))]
        shares = purchase_type_shares(items)
        assert shares.goods == Decimal("0.3")
        assert shares.services == Decimal("0.7")
        assert shares.unspecified == Decimal("0")
        assert shares.goods + shares.services + shares.unspecified == Decimal(1)

    def test_items_with_zero_amount(self):
        items = [_item("товар", Decimal("0")), _item("услуга", Decimal("0")), _item(None, None)]
        shares = purchase_type_shares(items)
        assert shares == TypeShares(goods=Decimal("0"), services=Decimal("0"), unspecified=Decimal("1"))

    def test_purchase_without_items(self):
        shares = purchase_type_shares([])
        assert shares == TypeShares(goods=Decimal("0"), services=Decimal("0"), unspecified=Decimal("1"))

    def test_shares_sum_to_one_with_thirds(self):
        # 100/100/100 — классический случай, где 1/3+1/3+1/3 не досчитывается
        # до 1 при прямом Decimal-делении на три части.
        items = [_item("товар", Decimal("100")), _item("услуга", Decimal("100")), _item(None, Decimal("100"))]
        shares = purchase_type_shares(items)
        assert shares.goods + shares.services + shares.unspecified == Decimal(1)


class TestSplitAmountByShares:
    def test_sums_exactly_to_amount(self):
        shares = purchase_type_shares([
            _item("товар", Decimal("100")), _item("услуга", Decimal("100")), _item(None, Decimal("100")),
        ])
        goods, services, unspecified = split_amount_by_shares(Decimal("10.00"), shares)
        assert goods + services + unspecified == Decimal("10.00")

    def test_all_in_biggest_share_when_no_items(self):
        shares = TypeShares(goods=Decimal(0), services=Decimal(0), unspecified=Decimal(1))
        goods, services, unspecified = split_amount_by_shares(Decimal("1234.56"), shares)
        assert (goods, services, unspecified) == (Decimal("0.00"), Decimal("0.00"), Decimal("1234.56"))

    def test_rounding_remainder_goes_to_biggest_part(self):
        shares = TypeShares(goods=Decimal("0.5"), services=Decimal("0.3"), unspecified=Decimal("0.2"))
        goods, services, unspecified = split_amount_by_shares(Decimal("0.01"), shares)
        assert goods + services + unspecified == Decimal("0.01")
        assert goods == Decimal("0.01")  # остаток целиком в самой большой доле


class TestSumByKind:
    def test_basic(self):
        rows = [("товар", Decimal("10")), ("услуга", Decimal("20")), ("работа", Decimal("5")), (None, Decimal("1")), ("?", None)]
        totals = sum_by_kind(rows)
        assert totals[KIND_GOODS] == Decimal("10")
        assert totals[KIND_SERVICES] == Decimal("25")
        assert totals[KIND_UNSPECIFIED] == Decimal("1")

    def test_empty(self):
        totals = sum_by_kind([])
        assert totals[KIND_GOODS] == Decimal("0")
        assert totals[KIND_SERVICES] == Decimal("0")
        assert totals[KIND_UNSPECIFIED] == Decimal("0")
