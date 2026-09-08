"""feo_plan_totals.py — итог по субсидии + пути/предки категорий дерева ФЭО.

Вынесено из feo_plan.py (рефакторинг без изменения поведения, сессия
2026-09-08, см. ПРАВИЛО №5). feo_plan_subsidy_totals — тонкая обёртка над
compute_feo_plan_tree (ПРАВИЛО №6 — не пересчитывать сумму заново).

leaf_used_totals — единственная реализация агрегата «использовано по листу
ФЭО» (contracted_used/planned_used через CONTRACTED_STATUSES/PLANNED_STATUSES
из app.routers.purchase_budget). Раньше идентичный SQL был продублирован в
GET /leaves и GET /budget-residuals (routers/feo_plan_reads_budget.py, сессия
2026-09-08) — оба теперь зовут эту функцию.
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.feo_plan_tree import compute_feo_plan_tree


async def feo_plan_subsidy_totals(
    db: AsyncSession, subsidy_ids: list[int]
) -> dict[int, float]:
    """Σ display корневых узлов (parent_id IS NULL) дерева ФЭО per субсидия —
    единственное число KPI «Запланировано» (used by _calculate_feo_planned_tree_bulk
    в subsidies.py и total_plan_combined в _create_plan_graph_version в
    purchases.py). Тонкая обёртка над compute_feo_plan_tree — см. её docstring
    за формулой.
    """
    result = {sid: 0.0 for sid in subsidy_ids}
    if not subsidy_ids:
        return result
    tree = await compute_feo_plan_tree(db, subsidy_ids)
    for node in tree.values():
        if node["parent_id"] is None:
            result[node["subsidy_id"]] = result.get(node["subsidy_id"], 0.0) + node["display"]
    return result


def build_category_path(cat, cat_by_id: dict) -> str:
    """Путь категории «Направление › Подкатегория › Лист» (сверху вниз).

    cat_by_id — {id: FeoCategory} для всех категорий той же субсидии
    (нужен для подъёма по parent_id без доп. запросов к БД).
    """
    if cat is None:
        return ""
    names = [cat.name]
    cur = cat
    while cur.parent_id is not None and cur.parent_id in cat_by_id:
        cur = cat_by_id[cur.parent_id]
        names.append(cur.name)
    return " › ".join(reversed(names))


async def leaf_used_totals(
    db: AsyncSession,
    leaf_ids: list[int],
    exclude_purchase_id: Optional[int] = None,
) -> dict[int, tuple[float, float]]:
    """{feo_category_id листа: (contracted_used, planned_used)}.

    contracted_used = SUM(PurchaseItem.total_price) по позициям листа, чья
    закупка в CONTRACTED_STATUSES; planned_used — та же сумма по
    PLANNED_STATUSES. exclude_purchase_id — исключить позиции этой закупки
    (форма редактирования закупки не должна учитывать свои же старые суммы).
    Пустой leaf_ids -> {} без обращения к БД.
    """
    if not leaf_ids:
        return {}

    from sqlalchemy import select, func as sqlfunc, case
    from app.models.purchase_item import PurchaseItem
    from app.models.purchase import Purchase as _Purchase
    from app.routers.purchase_budget import CONTRACTED_STATUSES, PLANNED_STATUSES

    used_q = (
        select(
            PurchaseItem.feo_category_id,
            sqlfunc.coalesce(
                sqlfunc.sum(case((_Purchase.status.in_(list(CONTRACTED_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("contracted_used"),
            sqlfunc.coalesce(
                sqlfunc.sum(case((_Purchase.status.in_(list(PLANNED_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("planned_used"),
        )
        .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
        .where(PurchaseItem.feo_category_id.in_(leaf_ids))
    )
    if exclude_purchase_id is not None:
        used_q = used_q.where(PurchaseItem.purchase_id != exclude_purchase_id)
    used_q = used_q.group_by(PurchaseItem.feo_category_id)

    result: dict[int, tuple[float, float]] = {}
    for r in (await db.execute(used_q)).all():
        result[r.feo_category_id] = (float(r.contracted_used), float(r.planned_used))
    return result


def build_ancestor_ids(cat, cat_by_id: dict) -> list:
    """id всех предков категории, от корня до непосредственного родителя (сверху вниз).

    Не включает саму `cat`. cat_by_id — {id: FeoCategory} той же субсидии (см.
    build_category_path). Нужен фронту (GET /feo-categories/plan-positions), чтобы
    находить плановые позиции вложенных конечных категорий по id родителя, выбранного
    в дереве, БЕЗ обхода обрезанного фронтового дерева (frontend/useFeoLeaves
    filterFundedNodes вырезает конечные узлы без собственного budget — см. баг «В этой
    категории нет плановых позиций», сессия 2026-08-05).
    """
    if cat is None:
        return []
    ids = []
    cur = cat
    while cur.parent_id is not None and cur.parent_id in cat_by_id:
        cur = cat_by_id[cur.parent_id]
        ids.append(cur.id)
    return list(reversed(ids))

