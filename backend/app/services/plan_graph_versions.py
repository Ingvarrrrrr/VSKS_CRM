"""Снапшоты дерева плана ФЭО (PlanGraphVersion) — версионирование плана закупок.

Вынесено из app/routers/purchases.py (Правило №5, модульность) без изменения
поведения. Единственная функция здесь — _create_plan_graph_version, вызываемая
и из ядра purchases.py (update_purchase), и из app/routers/purchase_items_edit.py
(patch_purchase_item/split/delete позиции) — общий источник правды для снапшота,
не дублировать логику построения дерева в двух местах (ПРАВИЛО №6).
"""
from typing import Optional
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.purchase_item import PurchaseItem


async def _create_plan_graph_version(
    subsidy_id: int,
    db: AsyncSession,
    user,
    note: Optional[str] = None,
    effective_date: Optional[date] = None,
) -> bool:
    """
    Build a snapshot of all active FeoPlannedItems for the subsidy with residuals
    and save as a new PlanGraphVersion row. Increments version_number.
    schema_version=2: includes recursive FeoCategory tree with budget.
    Returns True if a new version was created, False if deduplicated.
    Caller must commit after this call.
    """
    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    from app.models.feo_category import FeoCategory as _FC
    from app.models.plan_graph_version import PlanGraphVersion as _PGV
    from app.models.purchase import Purchase as _Purchase

    # Fetch all active FEO items for this subsidy
    items_q = (
        select(_FPI, _FC.id.label("cat_id"))
        .join(_FC, _FPI.feo_category_id == _FC.id)
        .where(_FC.subsidy_id == subsidy_id, _FPI.is_active == True)
        .order_by(_FPI.id)
    )
    rows = (await db.execute(items_q)).all()
    item_ids = [r[0].id for r in rows]

    # Версия строится из дерева ФЭО-категорий даже без FeoPlannedItem'ов
    # (субсидия может иметь только категории с бюджетом). Пустой рынок позиций
    # даёт пустые агрегаты, но дерево всё равно снапшотится ниже.
    used_map: dict[int, float] = {}
    used_actual_map: dict[int, float] = {}
    links_map: dict[int, list] = {}
    if item_ids:
        # Aggregate used amounts (all statuses)
        used_q = (
            select(
                PurchaseItem.feo_planned_item_id,
                func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
            )
            .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
            .group_by(PurchaseItem.feo_planned_item_id)
        )
        used_map = {
            r.feo_planned_item_id: float(r.used)
            for r in (await db.execute(used_q)).all()
        }

        # Aggregate used amounts (fact: only delivered/paid)
        used_actual_q = (
            select(
                PurchaseItem.feo_planned_item_id,
                func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
            )
            .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
            .where(
                PurchaseItem.feo_planned_item_id.in_(item_ids),
                _Purchase.status.in_(("delivered", "paid")),
            )
            .group_by(PurchaseItem.feo_planned_item_id)
        )
        used_actual_map = {
            r.feo_planned_item_id: float(r.used)
            for r in (await db.execute(used_actual_q)).all()
        }

        # Collect linked purchase ids
        links_q = (
            select(PurchaseItem.feo_planned_item_id, PurchaseItem.purchase_id)
            .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
        )
        for lr in (await db.execute(links_q)).all():
            links_map.setdefault(lr.feo_planned_item_id, [])
            if lr.purchase_id not in links_map[lr.feo_planned_item_id]:
                links_map[lr.feo_planned_item_id].append(lr.purchase_id)

    snapshot_items = []
    total_planned = 0.0
    total_used = 0.0
    for r in rows:
        item = r[0]
        planned = float(item.amount or 0)
        used = used_map.get(item.id, 0.0)
        used_actual = used_actual_map.get(item.id, 0.0)
        total_planned += planned
        total_used += used
        snapshot_items.append({
            "feo_item_id": item.id,
            "name": item.name,
            "category_id": item.feo_category_id,
            "planned_amount": planned,
            "used_amount": used,
            "used_actual_amount": used_actual,
            "residual": planned - used,
            "linked_purchase_ids": links_map.get(item.id, []),
        })

    # Build FeoCategory tree for schema_version=2
    cats_q = select(_FC).where(_FC.subsidy_id == subsidy_id).order_by(_FC.id)
    all_cats = (await db.execute(cats_q)).scalars().all()

    if not rows and not all_cats:
        return False  # ни позиций, ни категорий — версионировать нечего

    # FCAT-B3: aggregate used_amount via PurchaseItem.feo_category_id for leaf nodes
    all_cat_ids = [c.id for c in all_cats]
    cat_used_map: dict[int, float] = {}
    cat_used_actual_map: dict[int, float] = {}
    if all_cat_ids:
        cat_used_q = (
            select(
                PurchaseItem.feo_category_id,
                func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
            )
            .where(PurchaseItem.feo_category_id.in_(all_cat_ids))
            .group_by(PurchaseItem.feo_category_id)
        )
        cat_used_map = {
            r.feo_category_id: float(r.used)
            for r in (await db.execute(cat_used_q)).all()
        }

        cat_used_actual_q = (
            select(
                PurchaseItem.feo_category_id,
                func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
            )
            .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
            .where(
                PurchaseItem.feo_category_id.in_(all_cat_ids),
                _Purchase.status.in_(("delivered", "paid")),
            )
            .group_by(PurchaseItem.feo_category_id)
        )
        cat_used_actual_map = {
            r.feo_category_id: float(r.used)
            for r in (await db.execute(cat_used_actual_q)).all()
        }

    def _build_tree(cats, parent_id=None):
        nodes = []
        for c in cats:
            if c.parent_id == parent_id:
                nodes.append({
                    "id": c.id,
                    "name": c.name,
                    "level": c.level,
                    "code": c.code,
                    "appendix": c.appendix,
                    "budget": float(c.budget) if c.budget is not None else None,
                    "planned_amount": float(c.planned_amount) if c.planned_amount is not None else None,
                    "planned_quantity": float(c.planned_quantity) if c.planned_quantity is not None else None,
                    "unit": c.unit,
                    "used_amount": cat_used_map.get(c.id, 0.0),  # FCAT-B3: агрегат через feo_category_id
                    "used_actual_amount": cat_used_actual_map.get(c.id, 0.0),
                    "children": _build_tree(cats, parent_id=c.id),
                })
        return nodes

    feo_tree = _build_tree(all_cats)

    # Без FeoPlannedItem'ов план берём из бюджетов листовых категорий,
    # чтобы «Итого план» в списке редакций не было нулевым.
    if not snapshot_items:
        def _leaf_budget_sum(nodes):
            total = 0.0
            for n in nodes:
                children = n.get("children") or []
                if children:
                    total += _leaf_budget_sum(children)
                elif n.get("budget"):
                    total += float(n["budget"])
            return total
        total_planned = _leaf_budget_sum(feo_tree)

    # manual_plan_total — рекурсивно по дереву ФЭО (ручной план qty*amt или бюджет листа)
    def _node_manual_plan(n):
        own = 0.0
        qty = float(n.get("planned_quantity") or 0)
        amt = float(n.get("planned_amount") or 0)
        children = n.get("children") or []
        if qty > 0 and amt > 0:
            own = qty * amt
        elif not children and n.get("budget"):
            own = float(n["budget"])
        return own + sum(_node_manual_plan(c) for c in children)
    manual_plan_total = sum(_node_manual_plan(n) for n in feo_tree)

    # purchases_plan_total / purchases_calc_total — суммы закупок в статусах плана закупок.
    # ПРАВИЛО №6 (2026-09-06): раньше здесь была ТРЕТЬЯ по счёту копия цепочки
    # «сумма закупки по стадии» (своя, отличная и от purchase_amounts(), и от
    # effective_amount_expr() — например, для delivered/paid брала payment_amount
    # ИЛИ contract_price ИЛИ plan, минуя acceptance_doc_amount вовсе). Заменена
    # на bulk-загрузку app.services.purchase_amounts.load_purchase_amounts —
    # без N+1 (один набор запросов на весь список закупок субсидии).
    _PLAN_STATUSES = ("plan_schedule", "work_in_progress", "contracted", "ordered", "delivered", "paid")
    purch_rows = (await db.execute(
        select(_Purchase.id, _Purchase.status)
        .where(_Purchase.subsidy_id == subsidy_id, _Purchase.status.in_(_PLAN_STATUSES))
    )).all()
    from app.services.purchase_amounts import load_purchase_amounts as _load_purchase_amounts_snapshot
    _snapshot_purch_ids = [pr.id for pr in purch_rows]
    _snapshot_amounts = (
        await _load_purchase_amounts_snapshot(db, _snapshot_purch_ids) if _snapshot_purch_ids else {}
    )
    purchases_calc_total = sum(
        (
            float(_snapshot_amounts[pid].effective)
            if _snapshot_amounts.get(pid) and _snapshot_amounts[pid].effective is not None
            else 0.0
        )
        for pid in _snapshot_purch_ids
    )
    purchase_statuses = {str(pr.id): pr.status for pr in purch_rows}

    # purchases_plan_total — на уровне PurchaseItem (не Purchase.planned_total_price), чтобы
    # частично привязанная к плану закупка не тянула в снапшот всю свою сумму целиком, и
    # исключая позиции с feo_planned_item_id IS NOT NULL — они расходуют ручной план дерева
    # ФЭО (manual_plan_total), а не складываются с ним поверх.
    # (informational — плоская сумма по всей субсидии, без учёта дерева; для KPI-совместимой
    # величины см. total_plan_combined ниже)
    plan_item_total_q = (
        select(func.coalesce(func.sum(PurchaseItem.total_price), 0))
        .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
        .where(_Purchase.subsidy_id == subsidy_id)
        .where(_Purchase.status.in_(_PLAN_STATUSES))
        .where(PurchaseItem.feo_planned_item_id.is_(None))
    )
    purchases_plan_total = float((await db.execute(plan_item_total_q)).scalar() or 0)

    # total_effective = ручной план дерева ФЭО + фактические суммы закупок
    total_effective = manual_plan_total + purchases_calc_total

    # total_plan_combined — единая формула дерева ФЭО (app.services.feo_plan.
    # compute_feo_plan_tree/feo_plan_subsidy_totals), та же, что и в
    # _calculate_feo_planned_tree_bulk (subsidies.py) — единый источник KPI
    # «Запланировано». Раньше здесь была наивная сумма manual_plan_total +
    # purchases_plan_total — задваивала план, когда позиция закупки лежала
    # ОДНОВРЕМЕННО на группе и на её дочернем листе (см. docstring
    # compute_feo_plan_tree). Значение обязано совпадать с текущим KPI, иначе
    # история версий плана закупок расходится с тем, что видно на вкладке
    # «Субсидии».
    from app.services.feo_plan import feo_plan_subsidy_totals
    total_plan_combined = (await feo_plan_subsidy_totals(db, [subsidy_id])).get(subsidy_id, 0.0)

    snapshot = {
        "schema_version": 2,
        "subsidy_id": subsidy_id,
        "effective_date": effective_date.isoformat() if effective_date else None,
        "total_planned": total_planned,
        "total_used": total_used,
        "total_effective": total_effective,
        "manual_plan_total": manual_plan_total,
        "purchases_plan_total": purchases_plan_total,
        "purchases_calc_total": purchases_calc_total,
        "total_plan_combined": total_plan_combined,
        "purchase_statuses": purchase_statuses,
        "items": snapshot_items,  # backward-compat
        "tree": feo_tree,
    }

    # Dedup: skip if identical to last version (ignoring effective_date)
    last_ver_q = (
        select(_PGV)
        .where(_PGV.subsidy_id == subsidy_id)
        .order_by(_PGV.version_number.desc())
        .limit(1)
    )
    last_ver = (await db.execute(last_ver_q)).scalar_one_or_none()
    if last_ver is not None:
        prev_snap = {k: v for k, v in (last_ver.snapshot or {}).items() if k != "effective_date"}
        new_snap = {k: v for k, v in snapshot.items() if k != "effective_date"}
        if prev_snap == new_snap:
            return False

    # Get next version_number
    max_ver_q = select(
        func.coalesce(func.max(_PGV.version_number), 0)
    ).where(_PGV.subsidy_id == subsidy_id)
    next_ver = int((await db.execute(max_ver_q)).scalar() or 0) + 1

    pgv = _PGV(
        subsidy_id=subsidy_id,
        version_number=next_ver,
        created_by_id=getattr(user, "id", None),
        created_by_name=getattr(user, "full_name", None) or getattr(user, "username", None),
        snapshot=snapshot,
        note=note,
        effective_date=effective_date,
    )
    db.add(pgv)
    return True
