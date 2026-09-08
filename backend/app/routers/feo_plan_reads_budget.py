"""Read-only остатки бюджета ФЭО по листу/направлению (не по формуле плана).

Сосед feo_plan_reads.py, вынесенный из него в волне 3a (2026-09-08, Правило №5:
исходный feo_plan_reads.py разросся до 1016 строк). Несёт /leaves и
/budget-residuals — оба считают budget/contracted_used/planned_used по дереву
FeoCategory через CONTRACTED_STATUSES/PLANNED_STATUSES и
app.services.subsidy_budget.compute_budget_map (Правило №6 — та же рекурсия
budget узла, что и app.routers.subsidies.calculate_budget_from_categories),
в отличие от /plan-tree и /plan-positions (feo_plan_reads_tree.py), которые
строятся вокруг ДРУГОЙ формулы — app.services.feo_plan.compute_feo_plan_tree
(«заказ замещает план»).

Оба пути статичные (без {cat_id}) и, как и соседи, ОБЯЗАНЫ регистрироваться в
app/routes.py ДО feo_categories.router (несёт catch-all GET/PUT/DELETE
"/{cat_id}"). Гейт прав — через `from app.routers import feo_categories as fc;
fc._has_feo_action(...)`, чтобы monkeypatch в тестах продолжал работать
независимо от файла-обработчика.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.feo_category import FeoCategory
from app.auth.jwt import get_current_user
from app.routers import feo_categories as fc
# Правило №6: рекурсия «budget узла = собственный, иначе сумма детей» —
# единственная реализация, см. app.services.subsidy_budget (та же формула,
# что app.routers.subsidies.calculate_budget_from_categories).
from app.services.subsidy_budget import compute_budget_map
# Правило №6: агрегат «использовано по листу» — единственная реализация,
# см. app.services.feo_plan_totals.leaf_used_totals.
from app.services.feo_plan_totals import leaf_used_totals

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


@router.get("/leaves")
async def get_feo_leaves(
    subsidy_id: int = Query(...),
    exclude_purchase_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns leaf FeoCategory nodes (без детей) with aggregated used_amount via feo_category_id.

    Response: [{id, name, parent_id, level, budget, used_amount, residual, path}]
    where path = "Direction › Subcategory › LeafName".

    Право feo_budget.view_leaf (см. backend/app/__init__.py, дефолт — все роли,
    включая employee) гейтит денежные поля (budget, contracted_used, planned_used,
    uncontracted_remaining, spendable_remaining, used_amount, residual) — без права
    приходят 0, структура ответа не меняется (закрытие дыры: раньше эндпоинт вообще
    не проверял права, см. задачу владельца 2026-08-06).
    """
    can_view_leaf = await fc._has_feo_action(current_user, db, "feo_budget.view_leaf")
    from sqlalchemy import select

    # Все FeoCategory для subsidy
    cats_q = select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    all_cats = (await db.execute(cats_q)).scalars().all()
    if not all_cats:
        return []

    cat_by_id = {c.id: c for c in all_cats}
    children_count: dict[int, int] = {}
    for c in all_cats:
        if c.parent_id is not None:
            children_count[c.parent_id] = children_count.get(c.parent_id, 0) + 1

    # Leaves = категории у которых нет детей в feo_categories
    leaves = [c for c in all_cats if children_count.get(c.id, 0) == 0]
    if not leaves:
        return []

    leaf_ids = [c.id for c in leaves]

    # Правило №6: агрегат «использовано по листу» — единственная реализация,
    # см. app.services.feo_plan_totals.leaf_used_totals (тот же SQL что и в
    # /budget-residuals ниже).
    leaf_used_map = await leaf_used_totals(db, leaf_ids, exclude_purchase_id=exclude_purchase_id)

    # Build path "Direction › Subcategory › Leaf"
    def build_path(cat) -> str:
        names = [cat.name]
        cur = cat
        while cur.parent_id is not None and cur.parent_id in cat_by_id:
            cur = cat_by_id[cur.parent_id]
            names.append(cur.name)
        return " › ".join(reversed(names))

    result = []
    for c in leaves:
        budget = float(c.budget or 0)
        contracted_used, planned_used = leaf_used_map.get(c.id, (0.0, 0.0))
        uncontracted_remaining = budget - contracted_used
        spendable_remaining = budget - planned_used
        if not can_view_leaf:
            budget = contracted_used = planned_used = uncontracted_remaining = spendable_remaining = 0.0
        result.append({
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "level": c.level,
            "budget": budget,
            # New metrics
            "contracted_used": contracted_used,
            "planned_used": planned_used,
            "uncontracted_remaining": uncontracted_remaining,
            "spendable_remaining": spendable_remaining,
            # Legacy fields (kept for backward compat): used_amount = planned_used, residual = spendable_remaining
            "used_amount": planned_used,
            "residual": spendable_remaining,
            "path": build_path(c),
        })

    # Сортировка по path для удобства autocomplete
    result.sort(key=lambda x: x["path"])
    return result


@router.get("/budget-residuals")
async def feo_budget_residuals(
    subsidy_id: int = Query(...),
    category_ids: str = Query("", description="comma-separated leaf FeoCategory ids"),
    exclude_purchase_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Остатки бюджета по ФЭО для формы закупки.

    Для пользователей с feo_budget.view_all_levels возвращает направления (ур.1)
    и ancestors предков в каждом листе. Без этого права: directions=[],
    ancestors=[] — только сам листовой остаток.

    budget листа = FeoCategory.budget; used = SUM(PurchaseItem.total_price) по feo_category_id листа.
    Узел выше: budget = собственный .budget если задан, иначе сумма budget детей;
    used = сумма used всех листьев-потомков. residual = budget - used.
    Ответ: {directions:[{id,name,level,path,budget,used,residual}],
            leaves:[{id,name,level,path,budget,used,residual,ancestors:[...]}]}
    (ancestors — сверху вниз: ур.1 первым).
    """
    from app.auth.permissions import _get_effective, _active_org
    effective = await _get_effective(current_user, db, _active_org(current_user))
    can_view_all_levels = (current_user.role == "superadmin") or ("feo_budget.view_all_levels" in effective)
    from sqlalchemy import select as _sel

    ids = [int(x) for x in category_ids.split(",") if x.strip().isdigit()]
    all_cats = (await db.execute(
        _sel(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    if not all_cats:
        return {"directions": [], "leaves": []}
    cat_by_id = {c.id: c for c in all_cats}
    children: dict[int, list] = {}
    for c in all_cats:
        if c.parent_id is not None:
            children.setdefault(c.parent_id, []).append(c.id)
    leaf_ids_all = [c.id for c in all_cats if not children.get(c.id)]

    # Правило №6: тот же агрегат, что и /leaves выше.
    leaf_used = await leaf_used_totals(db, leaf_ids_all, exclude_purchase_id=exclude_purchase_id)

    def descendant_leaves(cid):
        ch = children.get(cid)
        if not ch:
            return [cid]
        out = []
        for x in ch:
            out.extend(descendant_leaves(x))
        return out

    # Правило №6: budget по каждому узлу — общая рекурсия (compute_budget_map),
    # не отдельная копия. Вычисляется один раз для всего дерева субсидии.
    budget_map = compute_budget_map(all_cats)

    def contracted_of(cid):
        return sum(leaf_used.get(l, (0.0, 0.0))[0] for l in descendant_leaves(cid))

    def planned_of(cid):
        return sum(leaf_used.get(l, (0.0, 0.0))[1] for l in descendant_leaves(cid))

    def node_info(cid):
        c = cat_by_id[cid]
        b = budget_map.get(cid, 0.0)
        cu = contracted_of(cid)
        pu = planned_of(cid)
        return {
            "id": cid, "name": c.name, "level": c.level,
            "budget": b,
            "contracted_used": cu,
            "planned_used": pu,
            "uncontracted_remaining": b - cu,
            "spendable_remaining": b - pu,
            # Legacy fields (backward compat): used = planned_used, residual = spendable_remaining
            "used": pu,
            "residual": b - pu,
        }

    def path_of(cid):
        names = []
        cur = cat_by_id.get(cid)
        while cur is not None:
            names.append(cur.name)
            cur = cat_by_id.get(cur.parent_id) if cur.parent_id else None
        return " › ".join(reversed(names))

    # Направления (ур.1) субсидии — только для пользователей с view_all_levels.
    directions = []
    if can_view_all_levels:
        # Порядок как во вкладке субсидии: sort_order, затем id (не алфавит)
        roots = [c for c in all_cats if c.level == 1 or c.parent_id is None]
        roots.sort(key=lambda c: (c.sort_order is None, c.sort_order or 0, c.id))
        for c in roots:
            d = node_info(c.id)
            d["path"] = path_of(c.id)
            directions.append(d)

    leaves = []
    for lid in ids:
        if lid not in cat_by_id:
            continue
        leaf = node_info(lid)
        leaf["path"] = path_of(lid)
        # ancestors только для пользователей с view_all_levels
        if can_view_all_levels:
            ancestors = []
            cur = cat_by_id[lid]
            while cur.parent_id and cur.parent_id in cat_by_id:
                cur = cat_by_id[cur.parent_id]
                ancestors.append(node_info(cur.id))
            leaf["ancestors"] = list(reversed(ancestors))
        else:
            leaf["ancestors"] = []
        leaves.append(leaf)
    return {"directions": directions, "leaves": leaves}
