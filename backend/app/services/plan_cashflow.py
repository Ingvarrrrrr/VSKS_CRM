"""plan_cashflow.py — разворачивание плановых позиций ФЭО в точки платежей.

Экспортирует:
  expand_planned_item(item)          -> list[tuple[date, Decimal]]
  aggregate_by_month(points)         -> dict[(year, month), Decimal]
  aggregate_by_quarter(points)       -> dict[(year, quarter), Decimal]
  cashflow_for_subsidy(db, sid)      -> dict[(year,month), Decimal]  (суммарно по субсидии)
  cashflow_for_subsidies(db, sids)   -> dict[sid, dict[(y,m), Decimal]]
  cashflow_with_directions(db, sid)  -> dict[direction_cat_id, dict[(y,m), Decimal]]
"""

import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem


# ---------------------------------------------------------------------------
# Арифметика месяцев (без dateutil)
# ---------------------------------------------------------------------------

def add_months(d: date, k: int) -> date:
    """Прибавить k месяцев к дате d. При переполнении — последний день месяца."""
    month = d.month - 1 + k          # 0-based
    year  = d.year + month // 12
    month = month % 12 + 1           # 1-based
    max_day = calendar.monthrange(year, month)[1]
    day = min(d.day, max_day)
    return date(year, month, day)


# ---------------------------------------------------------------------------
# Разворачивание одной позиции
# ---------------------------------------------------------------------------

def expand_planned_item(item: FeoPlannedItem) -> list[tuple[date, Decimal]]:
    """Развернуть плановую позицию в список (дата, сумма).

    monthly: monthly_start_date + k месяцев, monthly_amount — для k in range(months_count).
    one_time: если есть planned_date → [(planned_date, amount)]; иначе [].
    """
    mode = getattr(item, 'payment_mode', 'one_time') or 'one_time'

    if mode == 'monthly':
        start = item.monthly_start_date
        cnt   = item.months_count
        amt   = item.monthly_amount
        if start is None or not cnt or amt is None:
            # Недостаточно данных — ничего не разворачиваем
            return []
        amt_d = Decimal(str(amt))
        return [(add_months(start, k), amt_d) for k in range(int(cnt))]
    else:
        # one_time
        if item.planned_date is None:
            return []
        total = item.amount
        if total is None:
            return []
        return [(item.planned_date, Decimal(str(total)))]


# ---------------------------------------------------------------------------
# Агрегация
# ---------------------------------------------------------------------------

def aggregate_by_month(
    points: list[tuple[date, Decimal]],
) -> dict[tuple[int, int], Decimal]:
    """Суммировать по (year, month)."""
    result: dict[tuple[int, int], Decimal] = {}
    for d, amt in points:
        key = (d.year, d.month)
        result[key] = result.get(key, Decimal(0)) + amt
    return result


def aggregate_by_quarter(
    points: list[tuple[date, Decimal]],
) -> dict[tuple[int, int], Decimal]:
    """Суммировать по (year, quarter) где quarter = ceil(month/3)."""
    result: dict[tuple[int, int], Decimal] = {}
    for d, amt in points:
        q = (d.month - 1) // 3 + 1
        key = (d.year, q)
        result[key] = result.get(key, Decimal(0)) + amt
    return result


# ---------------------------------------------------------------------------
# Async-хелперы для работы с БД
# ---------------------------------------------------------------------------

async def _load_active_items_for_subsidies(
    db: AsyncSession,
    subsidy_ids: list[int],
) -> list[tuple[int, int, FeoPlannedItem]]:
    """Загрузить активные FeoPlannedItem + привязки к субсидии и direction (level-1 cat).

    Возвращает список (subsidy_id, direction_cat_id_or_0, item).
    direction_cat_id_or_0 = id FeoCategory level=1, предок позиции.
    """
    if not subsidy_ids:
        return []

    # Загружаем все категории нужных субсидий (для построения пути к корню)
    cats_result = await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id.in_(subsidy_ids))
    )
    cats = cats_result.scalars().all()
    cat_by_id: dict[int, FeoCategory] = {c.id: c for c in cats}

    def root_direction_id(cat_id: int) -> int:
        """Найти id level-1 предка для данной категории."""
        visited: set[int] = set()
        current_id: Optional[int] = cat_id
        last_lvl1: int = 0
        while current_id is not None:
            if current_id in visited:
                break
            visited.add(current_id)
            c = cat_by_id.get(current_id)
            if c is None:
                break
            if c.level == 1:
                last_lvl1 = c.id
                break
            current_id = c.parent_id
        return last_lvl1

    # Загружаем плановые позиции
    items_result = await db.execute(
        select(FeoPlannedItem)
        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(
            FeoCategory.subsidy_id.in_(subsidy_ids),
            FeoPlannedItem.is_active == True,
        )
    )
    items = items_result.scalars().all()

    result: list[tuple[int, int, FeoPlannedItem]] = []
    for item in items:
        cat = cat_by_id.get(item.feo_category_id)
        if cat is None:
            continue
        sid = cat.subsidy_id
        dir_id = root_direction_id(item.feo_category_id)
        result.append((sid, dir_id, item))

    return result


async def cashflow_for_subsidy(
    db: AsyncSession,
    subsidy_id: int,
) -> dict[tuple[int, int], Decimal]:
    """Помесячный плановый cash-flow субсидии (суммарно).

    Возвращает dict {(year, month): Decimal}.
    """
    triples = await _load_active_items_for_subsidies(db, [subsidy_id])
    all_points: list[tuple[date, Decimal]] = []
    for _, _, item in triples:
        all_points.extend(expand_planned_item(item))
    return aggregate_by_month(all_points)


async def cashflow_for_subsidies(
    db: AsyncSession,
    subsidy_ids: list[int],
) -> dict[int, dict[tuple[int, int], Decimal]]:
    """Cash-flow по набору субсидий: {subsidy_id: {(year,month): Decimal}}."""
    if not subsidy_ids:
        return {}
    triples = await _load_active_items_for_subsidies(db, subsidy_ids)
    result: dict[int, dict[tuple[int, int], Decimal]] = {sid: {} for sid in subsidy_ids}
    for sid, _, item in triples:
        for d, amt in expand_planned_item(item):
            key = (d.year, d.month)
            result[sid][key] = result[sid].get(key, Decimal(0)) + amt
    return result


async def cashflow_with_directions(
    db: AsyncSession,
    subsidy_id: int,
) -> dict[int, dict[tuple[int, int], Decimal]]:
    """Cash-flow субсидии с разбивкой по direction (level-1 категория).

    Возвращает {direction_cat_id: {(year, month): Decimal}}.
    direction_cat_id = 0 означает «без направления».
    """
    triples = await _load_active_items_for_subsidies(db, [subsidy_id])
    result: dict[int, dict[tuple[int, int], Decimal]] = {}
    for _, dir_id, item in triples:
        if dir_id not in result:
            result[dir_id] = {}
        per_dir = result[dir_id]
        for d, amt in expand_planned_item(item):
            key = (d.year, d.month)
            per_dir[key] = per_dir.get(key, Decimal(0)) + amt
    return result
