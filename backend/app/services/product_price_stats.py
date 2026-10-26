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

Часть 2 плана clever-bouncing-lantern.md (14.10) добавила СРЕДНЮЮ ПО РЕГИОНУ
И ПАРТИИ — необязательные target_region/quantity/product_unit. Без них
(старые вызовы) поведение НЕ меняется — тот же путь, что раньше (окно 60
дней/фолбэк 3, см. _all_regions_fallback). С ними — лестница уровней:
  region_batch → region → nearest_batch → nearest → batch → all
«Данных хватает» на фильтрованном уровне = ≥2 РАЗНЫХ договора (source_ref)
за последние 12 месяцев; единица позиции должна совпадать с product_unit
(если он передан) — иначе позиция не входит ни в один фильтрованный уровень
(она остаётся видна только на уровне "all", где фильтров нет вообще)."""
from dataclasses import dataclass
from datetime import date as _date, timedelta
from decimal import Decimal
from typing import Iterable, Optional, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

WINDOW_DAYS = 60
FALLBACK_COUNT = 3
REGIONAL_WINDOW_DAYS = 365
MIN_CONTRACTS_FOR_LEVEL = 2

BATCH_RANGES = (
    ("1-9", 1, 9),
    ("10-99", 10, 99),
    ("100-999", 100, 999),
    ("1000+", 1000, None),
)


class _HistoryRowLike(Protocol):
    price: Optional[Decimal]
    collected_at: Optional[_date]


@dataclass
class PriceStats:
    avg_price: Optional[Decimal]
    basis_count: int
    window_days: Optional[int]
    stale: bool
    from_date: Optional[_date]
    to_date: _date
    level: str = "all"
    region_used: Optional[str] = None
    batch: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "avg_price": self.avg_price,
            "basis_count": self.basis_count,
            "window_days": self.window_days,
            "stale": self.stale,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "level": self.level,
            "region_used": self.region_used,
            "batch": self.batch,
        }


def batch_label(quantity) -> Optional[str]:
    """Количество → метка партии (1–9 / 10–99 / 100–999 / 1000+), или None,
    если quantity пусто/не положительное — такую позицию нельзя отнести ни к
    одной партии, она не участвует в партийных уровнях фильтра."""
    if quantity is None:
        return None
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        return None
    if qty < 1:
        return None
    for label, lo, hi in BATCH_RANGES:
        if hi is None:
            if qty >= lo:
                return label
        elif lo <= qty <= hi:
            return label
    return None


def _norm_unit(u: Optional[str]) -> str:
    return (u or "").strip().casefold()


def _unit_matches(row_unit: Optional[str], product_unit: Optional[str]) -> bool:
    """Единица позиции совпадает с единицей товара. product_unit=None (у
    товара единица не задана) — сравнивать не с чем, позиция допускается
    в фильтрованные уровни (её собственная единица и есть точка отсчёта,
    раз у товара выбора нет)."""
    if product_unit is None:
        return True
    return bool(row_unit) and _norm_unit(row_unit) == _norm_unit(product_unit)


def _all_rule(history_rows: Iterable[_HistoryRowLike], today: _date) -> PriceStats:
    """Старое правило БЕЗ ФИЛЬТРА (owner, 2026-09-16) — буквально не менялось:
    окно 60 дней, иначе последние 3, иначе всё, что есть; stale на фолбэке."""
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
            stale=True, from_date=from_date, to_date=today, level="all",
        )

    total = sum((r.price for r in basis), start=Decimal("0"))
    avg = (total / len(basis)).quantize(Decimal("0.01"))
    return PriceStats(
        avg_price=avg, basis_count=len(basis), window_days=WINDOW_DAYS,
        stale=stale, from_date=from_date, to_date=today, level="all",
    )


def compute_price_stats(
    history_rows: Iterable[_HistoryRowLike],
    today: Optional[_date] = None,
    *,
    target_region: Optional[str] = None,
    quantity=None,
    product_unit: Optional[str] = None,
) -> PriceStats:
    """history_rows — строки ProductPriceHistory (или любые объекты с полями
    .price/.collected_at, опционально .region/.quantity/.unit/.source_ref)
    ОДНОГО товара.

    Без target_region И без quantity — поведение НЕ МЕНЯЛОСЬ (см. _all_rule).
    С любым из них — лестница уровней, описанная в докстринге модуля;
    фильтрованные уровни смотрят на последние 12 месяцев и требуют ≥2 разных
    договоров (source_ref), иначе уровень считается «данных не хватает» и
    поиск идёт на следующую ступень лестницы, вплоть до "all"."""
    today = today or _date.today()
    rows = list(history_rows)
    target_batch = batch_label(quantity)

    if not target_region and target_batch is None:
        return _all_rule(rows, today)

    year_ago = today - timedelta(days=REGIONAL_WINDOW_DAYS)

    def _recent(r) -> bool:
        return r.price is not None and r.collected_at is not None and year_ago <= r.collected_at <= today

    def _filtered(region: Optional[str], want_batch: bool) -> list:
        out = []
        for r in rows:
            if not _recent(r):
                continue
            if not _unit_matches(getattr(r, "unit", None), product_unit):
                continue
            if region is not None and getattr(r, "region", None) != region:
                continue
            if want_batch and batch_label(getattr(r, "quantity", None)) != target_batch:
                continue
            out.append(r)
        return out

    def _contract_count(rs: list) -> int:
        refs = {getattr(r, "source_ref", None) or id(r) for r in rs}
        return len(refs)

    def _build(rs: list, level: str, region_used: Optional[str], batch_used: Optional[str]) -> PriceStats:
        total = sum((r.price for r in rs), start=Decimal("0"))
        avg = (total / len(rs)).quantize(Decimal("0.01"))
        return PriceStats(
            avg_price=avg, basis_count=len(rs), window_days=None, stale=False,
            from_date=year_ago, to_date=today,
            level=level, region_used=region_used, batch=batch_used,
        )

    # 1) регион + партия
    if target_region and target_batch:
        rs = _filtered(target_region, want_batch=True)
        if _contract_count(rs) >= MIN_CONTRACTS_FOR_LEVEL:
            return _build(rs, "region_batch", target_region, target_batch)

    # 2) регион
    if target_region:
        rs = _filtered(target_region, want_batch=False)
        if _contract_count(rs) >= MIN_CONTRACTS_FOR_LEVEL:
            return _build(rs, "region", target_region, None)

    # 3/4) ближайший регион с данными (+ партия, затем без партии)
    if target_region:
        candidate_regions = sorted({getattr(r, "region", None) for r in rows if getattr(r, "region", None)})
        candidate_regions = [r for r in candidate_regions if r != target_region]
        if candidate_regions:
            from app.services.region_distance import nearest_regions
            ordered = nearest_regions(target_region, candidate_regions)
            if target_batch:
                for cand in ordered:
                    rs = _filtered(cand, want_batch=True)
                    if _contract_count(rs) >= MIN_CONTRACTS_FOR_LEVEL:
                        return _build(rs, "nearest_batch", cand, target_batch)
            for cand in ordered:
                rs = _filtered(cand, want_batch=False)
                if _contract_count(rs) >= MIN_CONTRACTS_FOR_LEVEL:
                    return _build(rs, "nearest", cand, None)

    # 5) партия без региона
    if target_batch:
        rs = _filtered(None, want_batch=True)
        if _contract_count(rs) >= MIN_CONTRACTS_FOR_LEVEL:
            return _build(rs, "batch", None, target_batch)

    # 6) без фильтра — нынешнее правило, не менялось
    return _all_rule(rows, today)


async def compute_price_stats_bulk(
    db: AsyncSession,
    product_ids: list[int],
    today: Optional[_date] = None,
    *,
    target_region: Optional[str] = None,
    quantity=None,
) -> dict[int, PriceStats]:
    """Тот же расчёт (`compute_price_stats`) сразу для НЕСКОЛЬКИХ товаров —
    двумя SELECT (не N+1), для списков товаров (ProductOut.avg_price и т.п.).
    target_region/quantity — ОДНИ И ТЕ ЖЕ для всего списка (как в списке
    «Товары»: регион организации пользователя + партия 1–9, план
    clever-bouncing-lantern.md п.7); product_unit берётся из Product.unit
    КАЖДОГО товара отдельно (единица — своя у каждого товара)."""
    if not product_ids:
        return {}
    from app.models.product import Product
    from app.models.product_price_history import ProductPriceHistory
    from app.utils.chunking import chunked

    # Владелец, 26.10.2026: каталог дорос до 53 797 товаров — один IN на ВСЕ
    # id разом ловил asyncpg "the number of query arguments cannot exceed
    # 32767" (GET /api/products/ падал 500). Оба запроса — порциями по
    # DEFAULT_CHUNK_SIZE id, результат склеивается — число и состав строк
    # не меняются относительно одного большого IN.
    rows = []
    for ids_chunk in chunked(product_ids):
        rows.extend((await db.execute(
            select(
                ProductPriceHistory.product_id,
                ProductPriceHistory.price,
                ProductPriceHistory.collected_at,
                ProductPriceHistory.region,
                ProductPriceHistory.quantity,
                ProductPriceHistory.unit,
                ProductPriceHistory.source_ref,
            ).where(ProductPriceHistory.product_id.in_(ids_chunk))
        )).all())

    units: dict = {}
    for ids_chunk in chunked(product_ids):
        units.update(dict((await db.execute(
            select(Product.id, Product.unit).where(Product.id.in_(ids_chunk))
        )).all()))

    by_product: dict[int, list] = {pid: [] for pid in product_ids}
    for r in rows:
        by_product.setdefault(r.product_id, []).append(r)

    return {
        pid: compute_price_stats(
            group, today=today,
            target_region=target_region, quantity=quantity,
            product_unit=units.get(pid),
        )
        for pid, group in by_product.items()
    }
