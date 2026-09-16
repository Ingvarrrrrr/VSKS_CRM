"""Владелец, 2026-09-16, п.4/C: средняя цена товара — ОДНА функция
app.services.product_price_stats.compute_price_stats.

  «Средняя цена: все цены за последние 60 дней (по collected_at); если за 60
  дней нет ни одной — последние 3 (или сколько есть) с признаком stale=true.
  Всегда возвращать basis_count.»

Чистая функция без БД — история подаётся как список простых объектов с
.price/.collected_at (ProductPriceHistory-подобных).
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import pytest

from app.services.product_price_stats import compute_price_stats


@dataclass
class _Row:
    price: Optional[Decimal]
    collected_at: Optional[date]


TODAY = date(2026, 9, 16)


def _days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def test_one_price_in_window():
    rows = [_Row(Decimal("100"), _days_ago(10))]
    stats = compute_price_stats(rows, today=TODAY)
    assert stats.avg_price == Decimal("100.00")
    assert stats.basis_count == 1
    assert stats.stale is False
    assert stats.window_days == 60


def test_two_prices_in_window_average():
    rows = [_Row(Decimal("100"), _days_ago(10)), _Row(Decimal("200"), _days_ago(5))]
    stats = compute_price_stats(rows, today=TODAY)
    assert stats.avg_price == Decimal("150.00")
    assert stats.basis_count == 2
    assert stats.stale is False


def test_seven_prices_in_window_all_used():
    rows = [_Row(Decimal(str(100 * i)), _days_ago(i)) for i in range(1, 8)]
    stats = compute_price_stats(rows, today=TODAY)
    assert stats.basis_count == 7
    assert stats.stale is False
    expected_avg = (Decimal(str(sum(100 * i for i in range(1, 8)))) / 7).quantize(Decimal("0.01"))
    assert stats.avg_price == expected_avg


def test_outside_window_falls_back_to_last_three_stale():
    # Все строки старше 60 дней — окно пустое, берём последние (по дате) 3 из 5.
    rows = [_Row(Decimal(str(100 * i)), _days_ago(60 + i)) for i in range(1, 6)]
    stats = compute_price_stats(rows, today=TODAY)
    assert stats.stale is True
    assert stats.basis_count == 3
    # Последние по collected_at (наименьшее смещение = самые свежие среди старых)
    newest_three = sorted(rows, key=lambda r: r.collected_at, reverse=True)[:3]
    expected_avg = (sum((r.price for r in newest_three), start=Decimal("0")) / 3).quantize(Decimal("0.01"))
    assert stats.avg_price == expected_avg


def test_outside_window_fewer_than_three_uses_all():
    rows = [_Row(Decimal("500"), _days_ago(90)), _Row(Decimal("700"), _days_ago(100))]
    stats = compute_price_stats(rows, today=TODAY)
    assert stats.stale is True
    assert stats.basis_count == 2
    assert stats.avg_price == Decimal("600.00")


def test_no_history_at_all():
    stats = compute_price_stats([], today=TODAY)
    assert stats.avg_price is None
    assert stats.basis_count == 0
    assert stats.stale is True


def test_rows_without_collected_at_or_price_are_ignored():
    rows = [
        _Row(None, _days_ago(5)),
        _Row(Decimal("100"), None),
        _Row(Decimal("300"), _days_ago(5)),
    ]
    stats = compute_price_stats(rows, today=TODAY)
    assert stats.basis_count == 1
    assert stats.avg_price == Decimal("300.00")
    assert stats.stale is False


@pytest.mark.asyncio
async def test_compute_price_stats_bulk_matches_single(db_session, test_org):
    """compute_price_stats_bulk (список товаров, 1 запрос) считает ТЕМ ЖЕ
    compute_price_stats, что и одиночный эндпоинт — не вторая формула."""
    from app.models.product import Product
    from app.models.product_price_history import ProductPriceHistory
    from app.services.product_price_stats import compute_price_stats_bulk

    p1 = Product(name="Товар A", category="Прочее")
    p2 = Product(name="Товар B", category="Прочее")
    db_session.add_all([p1, p2])
    await db_session.commit()
    await db_session.refresh(p1)
    await db_session.refresh(p2)

    db_session.add_all([
        ProductPriceHistory(product_id=p1.id, price=Decimal("100"), collected_at=date.today(), source="manual"),
        ProductPriceHistory(product_id=p1.id, price=Decimal("200"), collected_at=date.today(), source="manual"),
        # p2 has no history at all
    ])
    await db_session.commit()

    stats_by_id = await compute_price_stats_bulk(db_session, [p1.id, p2.id])
    assert stats_by_id[p1.id].avg_price == Decimal("150.00")
    assert stats_by_id[p1.id].basis_count == 2
    assert stats_by_id[p2.id].basis_count == 0
    assert stats_by_id[p2.id].avg_price is None
