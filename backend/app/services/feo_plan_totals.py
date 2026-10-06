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
    db: AsyncSession, subsidy_ids: list[int], *, tree: Optional[dict] = None,
) -> dict[int, float]:
    """Σ display корневых узлов (parent_id IS NULL) дерева ФЭО per субсидия —
    единственное число KPI «Запланировано» (used by _calculate_feo_planned_tree_bulk
    в subsidies.py и total_plan_combined в _create_plan_graph_version в
    purchases.py). Тонкая обёртка над compute_feo_plan_tree — см. её docstring
    за формулой.

    `tree` — опционально уже посчитанный compute_feo_plan_tree(db, subsidy_ids)
    ЭТОГО ЖЕ вызова (ускорение 06.10.2026, координатор — GET /dashboard/charts?
    type_split=true строил дерево ТРИЖДЫ на один запрос: здесь + дважды внутри
    subsidy_type_totals/себя самой из _calculate_feo_planned_tree_bulk(type_split=
    True); см. её докстринг). Без аргумента — поведение прежнее (строит сама),
    существующие вызовы не меняются."""
    result = {sid: 0.0 for sid in subsidy_ids}
    if not subsidy_ids:
        return result
    if tree is None:
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
    FACT_ELIGIBLE_STATUSES. exclude_purchase_id — исключить позиции этой
    закупки (форма редактирования закупки не должна учитывать свои же старые
    суммы). Пустой leaf_ids -> {} без обращения к БД.

    Категория позиции — COALESCE(PurchaseItem.feo_category_id,
    Purchase.feo_category_id), та же привязка «позиция или шапка», что и везде
    в проекте (см. app.services.feo_plan_fact, app.services.purchase_feo_checks,
    app.services.plan_graph_export_data — ПРАВИЛО №6). До фикса (баг владельца
    2026-09-30, закупка РЕЕ-2026-00913) группировка шла по «голому»
    PurchaseItem.feo_category_id — закупки, у которых категория проставлена
    только в шапке (Purchase.feo_category_id), а не на позициях, вообще не
    попадали в used_map → «Ост.» на форме закупки показывал весь бюджет листа,
    игнорируя чужие закупки той же категории.

    planned_used (→ residual/spendable_remaining, то, что показывает «Ост.» на
    форме закупки) обязан считать РОВНО те же статусы, что и поле `fact` в
    каноничном дереве ФЭО (app.services.feo_plan_tree.compute_feo_plan_tree →
    app.services.feo_plan_fact.fact_consumption_by_category) — Правило №6,
    импортируем FACT_ELIGIBLE_STATUSES оттуда, не копируем набор. До этой
    правки (доработка владельца 2026-09-30) здесь стоял PLANNED_STATUSES
    (app.routers.purchase_budget) — он ШИРЕ: включает статус 'wishes' не
    входит, но НЕ совпадает с fact по составу (были расхождения на категории
    124 «Ремонт техники»: закупка №841 в статусе 'wishes' 4 000 ₽ попадала в
    planned_used, хотя compute_feo_plan_tree.fact её не считает).
    """
    if not leaf_ids:
        return {}

    from sqlalchemy import select, func as sqlfunc, case
    from app.models.purchase_item import PurchaseItem
    from app.models.purchase import Purchase as _Purchase
    from app.routers.purchase_budget import CONTRACTED_STATUSES
    from app.services.feo_plan_fact import FACT_ELIGIBLE_STATUSES

    cat_col = sqlfunc.coalesce(PurchaseItem.feo_category_id, _Purchase.feo_category_id)
    used_q = (
        select(
            cat_col.label("cat_id"),
            sqlfunc.coalesce(
                sqlfunc.sum(case((_Purchase.status.in_(list(CONTRACTED_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("contracted_used"),
            sqlfunc.coalesce(
                sqlfunc.sum(case((_Purchase.status.in_(list(FACT_ELIGIBLE_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("planned_used"),
        )
        .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
        .where(cat_col.in_(leaf_ids))
    )
    if exclude_purchase_id is not None:
        used_q = used_q.where(PurchaseItem.purchase_id != exclude_purchase_id)
    used_q = used_q.group_by(cat_col)

    result: dict[int, tuple[float, float]] = {}
    for r in (await db.execute(used_q)).all():
        result[r.cat_id] = (float(r.contracted_used), float(r.planned_used))
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

