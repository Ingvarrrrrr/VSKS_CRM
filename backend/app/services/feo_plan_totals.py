"""feo_plan_totals.py — итог по субсидии + пути/предки категорий дерева ФЭО.

Вынесено из feo_plan.py (рефакторинг без изменения поведения, сессия
2026-09-08, см. ПРАВИЛО №5). feo_plan_subsidy_totals — тонкая обёртка над
compute_feo_plan_tree (ПРАВИЛО №6 — не пересчитывать сумму заново).
"""
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

