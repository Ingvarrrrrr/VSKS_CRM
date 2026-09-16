"""Средняя цена товара по истории — ОДНА функция-источник (ПРАВИЛО №6,
владелец 2026-09-16): «Средняя цена: все цены за последние 60 дней (по
collected_at); если за 60 дней нет ни одной — последние 3 (или сколько есть)
с признаком stale=true. Всегда возвращать basis_count.»

`compute_price_stats` — чистая функция без обращений к БД (получает уже
загруженные строки истории): и одиночный эндпоинт (GET .../price-stats), и
пакетный расчёт для списка (`compute_price_stats_bulk`) считают ЧЕРЕЗ НЕЁ —
не заводим вторую формулу для списка (см. память проекта
feedback_single_source_of_truth: цена за единицу плановой позиции когда-то
считалась в шести местах, средняя цена товара не должна повторить это).
"""
from dataclasses import dataclass
from datetime import date as _date, timedelta
from decimal import Decimal
from typing import Iterable, Optional, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

WINDOW_DAYS = 60
FALLBACK_COUNT = 3


class _HistoryRowLike(Protocol):
    price: Optional[Decimal]
    collected_at: Optional[_date]


@dataclass
class PriceStats:
    avg_price: Optional[Decimal]
    basis_count: int
    window_days: int
    stale: bool
    from_date: Optional[_date]
    to_date: _date

    def as_dict(self) -> dict:
        return {
            "avg_price": self.avg_price,
            "basis_count": self.basis_count,
            "window_days": self.window_days,
            "stale": self.stale,
            "from_date": self.from_date,
            "to_date": self.to_date,
        }


def compute_price_stats(history_rows: Iterable[_HistoryRowLike], today: Optional[_date] = None) -> PriceStats:
    """history_rows — строки ProductPriceHistory (или любые объекты с полями
    .price/.collected_at) ОДНОГО товара. Строки без collected_at ИЛИ без price
    в расчёт не идут — усреднить/датировать их нечем.

    Правило (владелец, 2026-09-16):
      1) окно — все строки с collected_at в [today-60, today];
      2) если окно пусто — последние (по collected_at) до 3 строк из ВСЕХ,
         помечаем stale=true;
      3) если строк вообще нет — avg_price=None, basis_count=0, stale=true
         (нечего показать, ноль оснований).
    """
    today = today or _date.today()
    from_date = today - timedelta(days=WINDOW_DAYS)

    dated = [
        r for r in history_rows
        if r.collected_at is not None and r.price is not None
    ]

    in_window = sorted(
        (r for r in dated if from_date <= r.collected_at <= today),
        key=lambda r: r.collected_at,
    )

    if in_window:
        basis = in_window
        stale = False
    else:
        basis = sorted(dated, key=lambda r: r.collected_at, reverse=True)[:FALLBACK_COUNT]
        stale = True

    if not basis:
        return PriceStats(
            avg_price=None, basis_count=0, window_days=WINDOW_DAYS,
            stale=True, from_date=from_date, to_date=today,
        )

    total = sum((r.price for r in basis), start=Decimal("0"))
    avg = (total / len(basis)).quantize(Decimal("0.01"))
    return PriceStats(
        avg_price=avg, basis_count=len(basis), window_days=WINDOW_DAYS,
        stale=stale, from_date=from_date, to_date=today,
    )


async def compute_price_stats_bulk(
    db: AsyncSession,
    product_ids: list[int],
    today: Optional[_date] = None,
) -> dict[int, PriceStats]:
    """Тот же расчёт (`compute_price_stats`) сразу для НЕСКОЛЬКИХ товаров —
    одним SELECT (не N+1), для списков товаров (ProductOut.avg_price и т.п.).
    Группировка по product_id и вызов compute_price_stats на группу — формула
    не дублируется, только батчится доступ к БД."""
    if not product_ids:
        return {}
    from app.models.product_price_history import ProductPriceHistory

    rows = (await db.execute(
        select(
            ProductPriceHistory.product_id,
            ProductPriceHistory.price,
            ProductPriceHistory.collected_at,
        ).where(ProductPriceHistory.product_id.in_(product_ids))
    )).all()

    by_product: dict[int, list] = {pid: [] for pid in product_ids}
    for r in rows:
        by_product.setdefault(r.product_id, []).append(r)

    return {
        pid: compute_price_stats(group, today=today)
        for pid, group in by_product.items()
    }
