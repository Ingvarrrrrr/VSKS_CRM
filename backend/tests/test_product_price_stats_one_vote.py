"""Задача 3 (owner, 27.10.2026, product_merge): «один магазин — один голос»
в средней цене — среди source='import' строк с contractor_id оставляется
только самая свежая на каждый contractor_id, иначе магазин, загруженный
импортом несколько раз, весит больше других. compute_price_stats —
единственная формула (app/services/product_price_stats.py)."""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import pytest

from app.services.product_price_stats import compute_price_stats

TODAY = date(2026, 10, 27)


@dataclass
class _Row:
    price: Optional[Decimal]
    collected_at: Optional[date]
    source: Optional[str] = None
    contractor_id: Optional[int] = None
    id: Optional[int] = None


def _days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def test_contractor_loaded_three_times_counts_once_latest():
    rows = [
        # Магазин 1 (contractor_id=1) загружен import'ом ТРИЖДЫ с разными
        # ценами — должна остаться только самая свежая (collected_at=1).
        _Row(Decimal("100"), _days_ago(10), "import", 1, 1),
        _Row(Decimal("110"), _days_ago(5), "import", 1, 2),
        _Row(Decimal("120"), _days_ago(1), "import", 1, 3),
        # Магазин 2 и магазин 3 — по одной строке каждый.
        _Row(Decimal("200"), _days_ago(3), "import", 2, 4),
        _Row(Decimal("300"), _days_ago(2), "import", 3, 5),
    ]
    stats = compute_price_stats(rows, today=TODAY)
    # basis = {120 (магазин 1, самая свежая), 200 (магазин 2), 300 (магазин 3)}
    assert stats.basis_count == 3
    expected_avg = (Decimal("120") + Decimal("200") + Decimal("300")) / 3
    assert stats.avg_price == expected_avg.quantize(Decimal("0.01"))


def test_rows_without_contractor_or_non_import_not_deduped():
    rows = [
        _Row(Decimal("100"), _days_ago(10), "contract", None, 1),
        _Row(Decimal("100"), _days_ago(9), "contract", None, 2),
        _Row(Decimal("50"), _days_ago(8), "import", None, 3),
        _Row(Decimal("50"), _days_ago(7), "import", None, 4),
    ]
    stats = compute_price_stats(rows, today=TODAY)
    # ни одна строка не дедуплицируется (нет contractor_id или source не import)
    assert stats.basis_count == 4


def test_tie_break_by_id_when_dates_equal():
    rows = [
        _Row(Decimal("111"), _days_ago(1), "import", 1, 10),
        _Row(Decimal("222"), _days_ago(1), "import", 1, 11),  # тот же день, больший id — побеждает
    ]
    stats = compute_price_stats(rows, today=TODAY)
    assert stats.basis_count == 1
    assert stats.avg_price == Decimal("222.00")
