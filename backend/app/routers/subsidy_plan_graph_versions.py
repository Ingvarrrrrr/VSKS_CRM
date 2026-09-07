"""Версии плана-графика (plan-graph) субсидии — список/детали/создание.

Вынесено из app/routers/subsidies.py (Правило №5, рефакторинг 2026-09-07):
GET .../plan-graph/versions, GET .../versions/{version_id:int} (+
?with_reconciliation), POST .../versions (ручная публикация версии).

Node-matching хелперы (`_match_feo_nodes`, `_normalize_name`) физически жили
рядом с Compare-эндпоинтами в исходном файле, но переехали сюда, т.к.
`get_plan_graph_version` (?with_reconciliation=true) тоже их использует;
subsidy_plan_graph_compare.py импортирует их отсюда как общий источник
истины (ПРАВИЛО №6 — не дублировать сопоставление узлов дерева).

Собственный APIRouter на префиксе /api/subsidies — регистрируется в
app/routes.py рядом с subsidies.router.
"""
import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.auth.jwt import get_current_user, require_role, get_org_filter, ADMIN_ROLES
from app.models.user import User
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])


# ── Plan-Graph Version endpoints (Phase 12-03) ────────────────────────────────

def _snapshot_effective_total(snapshot: dict) -> float:
    """Compute total_effective from snapshot: fact replaces plan where fact > 0."""
    if snapshot.get("total_effective") is not None:
        return float(snapshot["total_effective"])
    items = snapshot.get("items") or []
    if items:
        return sum(
            (float(it.get("used_actual_amount") or 0) if float(it.get("used_actual_amount") or 0) > 0
             else float(it.get("planned_amount") or 0))
            for it in items
        )
    def _leaf_effective(nodes):
        total = 0.0
        for n in nodes:
            children = n.get("children") or []
            if children:
                total += _leaf_effective(children)
            else:
                ua = float(n.get("used_actual_amount") or 0)
                total += ua if ua > 0 else float(n.get("budget") or 0)
        return total
    return _leaf_effective(snapshot.get("tree") or [])


@router.get("/{subsidy_id}/plan-graph/versions")
async def list_plan_graph_versions(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return list of plan-graph versions for a subsidy (summary, no full snapshot)."""
    from app.models.plan_graph_version import PlanGraphVersion as _PGV

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа к субсидии")

    vers = (await db.execute(
        select(_PGV)
        .where(_PGV.subsidy_id == subsidy_id)
        .order_by(_PGV.version_number.desc())
        .limit(100)
    )).scalars().all()

    out = []
    for v in vers:
        snap = v.snapshot or {}
        out.append({
            "id": v.id,
            "version_number": v.version_number,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "created_by_name": v.created_by_name,
            "note": v.note,
            "effective_date": v.effective_date.isoformat() if v.effective_date else None,
            "total_planned": snap.get("total_plan_combined", snap.get("total_planned", 0)),
            "total_used": snap.get("total_used", 0),
            "total_effective": _snapshot_effective_total(snap),
            "item_count": len(snap.get("items", [])),
        })
    return out


@router.get("/{subsidy_id}/plan-graph/versions/{version_id:int}")
async def get_plan_graph_version(
    subsidy_id: int,
    version_id: int,
    with_reconciliation: bool = Query(False, description="Добавить факт по текущим закупкам"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return full snapshot for a specific plan-graph version.

    Optional ?with_reconciliation=true adds current actual PurchaseItem totals
    matched to snapshot tree nodes via composite-key matcher.
    """
    from app.models.plan_graph_version import PlanGraphVersion as _PGV

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа к субсидии")

    ver = (await db.execute(
        select(_PGV).where(
            _PGV.id == version_id,
            _PGV.subsidy_id == subsidy_id,
        )
    )).scalar_one_or_none()

    if not ver:
        raise HTTPException(404, "Версия плана закупок не найдена")

    resp = {
        "id": ver.id,
        "subsidy_id": ver.subsidy_id,
        "version_number": ver.version_number,
        "created_at": ver.created_at.isoformat() if ver.created_at else None,
        "created_by_id": ver.created_by_id,
        "created_by_name": ver.created_by_name,
        "note": ver.note,
        "effective_date": ver.effective_date.isoformat() if ver.effective_date else None,
        "snapshot": ver.snapshot,
    }

    if with_reconciliation:
        snap = ver.snapshot or {}
        snap_tree = snap.get("tree")
        reconciliation: dict = {}

        if snap_tree:
            from app.models.feo_planned_item import FeoPlannedItem as _FPI
            from app.models.purchase_item import PurchaseItem as _PI

            # Load current live FeoCategory tree for this subsidy
            live_cats = (await db.execute(
                select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(FeoCategory.id)
            )).scalars().all()

            def _build_live_tree_simple(cats, parent_id=None):
                nodes = []
                for c in cats:
                    if c.parent_id == parent_id:
                        nodes.append({
                            "id": c.id,
                            "name": c.name,
                            "level": c.level,
                            "code": c.code,
                            "children": _build_live_tree_simple(cats, parent_id=c.id),
                        })
                return nodes

            live_tree = _build_live_tree_simple(list(live_cats))
            live_cats_by_id = {c.id: c for c in live_cats}

            # Match snapshot tree → live tree
            match_result = _match_feo_nodes(snap_tree, live_tree)
            # match_result["matches"] = [(snap_node, live_node, match_type), ...]

            # For each live category, get PurchaseItem totals via FeoPlannedItem OR feo_category_id
            live_cat_ids = [c.id for c in live_cats]
            # FCAT-B3: SUM via feo_planned_item_id (legacy) + feo_category_id (new)
            cat_actual_map: dict[int, float] = {}
            if live_cat_ids:
                # Source 1: via FeoPlannedItem join (legacy ФАДМ_2026)
                actual_rows_via_fpi = (await db.execute(
                    select(
                        _FPI.feo_category_id,
                        func.coalesce(func.sum(_PI.total_price), 0).label("actual"),
                    )
                    .join(_PI, _PI.feo_planned_item_id == _FPI.id)
                    .where(_FPI.feo_category_id.in_(live_cat_ids))
                    .group_by(_FPI.feo_category_id)
                )).all()
                for r in actual_rows_via_fpi:
                    cat_actual_map[r.feo_category_id] = float(r.actual)

                # Source 2: via PurchaseItem.feo_category_id (FCAT-B1 new column)
                actual_rows_via_cat = (await db.execute(
                    select(
                        _PI.feo_category_id,
                        func.coalesce(func.sum(_PI.total_price), 0).label("actual"),
                    )
                    .where(_PI.feo_category_id.in_(live_cat_ids))
                    .group_by(_PI.feo_category_id)
                )).all()
                for r in actual_rows_via_cat:
                    cat_id = r.feo_category_id
                    cat_actual_map[cat_id] = cat_actual_map.get(cat_id, 0.0) + float(r.actual)

            def _subtree_actual(cat_id: int) -> float:
                """Recursively sum actual from cat and all its descendants."""
                total = cat_actual_map.get(cat_id, 0.0)
                cat = live_cats_by_id.get(cat_id)
                if cat:
                    for child in live_cats:
                        if child.parent_id == cat_id:
                            total += _subtree_actual(child.id)
                return total

            # Build reconciliation map keyed by snapshot node id
            for snap_node, live_node, match_type in match_result["matches"]:
                snap_id = snap_node.get("id")
                if snap_id is None:
                    continue
                live_id = live_node.get("id")
                budget_snap = float(snap_node.get("budget") or 0)
                actual = _subtree_actual(live_id) if live_id else 0.0
                reconciliation[str(snap_id)] = {
                    "matched_current_id": live_id,
                    "actual_used": round(actual, 2),
                    "actual_residual": round(budget_snap - actual, 2),
                    "match_type": match_type,
                }

            # Unmatched snapshot nodes → null
            for snap_node in match_result["only_a"]:
                snap_id = snap_node.get("id")
                if snap_id is not None:
                    reconciliation[str(snap_id)] = {
                        "matched_current_id": None,
                        "actual_used": 0.0,
                        "actual_residual": float(snap_node.get("budget") or 0),
                        "match_type": None,
                    }

        resp["reconciliation"] = reconciliation

    return resp


class PlanGraphVersionCreate(BaseModel):
    note: Optional[str] = None
    effective_date: Optional[date] = None


@router.post("/{subsidy_id}/plan-graph/versions")
async def create_plan_graph_version_manual(
    subsidy_id: int,
    body: PlanGraphVersionCreate = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    """Manually publish a plan-graph version (admin only)."""
    from app.routers.purchases import _create_plan_graph_version
    body = body or PlanGraphVersionCreate()
    await _create_plan_graph_version(
        subsidy_id,
        db,
        current_user,
        note=body.note or "Ручная публикация",
        effective_date=body.effective_date,
    )
    await db.commit()
    return {"ok": True, "message": "Версия плана закупок сохранена"}
def _normalize_name(name: str) -> str:
    """Normalize FeoCategory name for matching: lowercase, strip, collapse spaces."""
    return re.sub(r"\s+", " ", (name or "").lower().strip())


def _match_feo_nodes(tree_a: list, tree_b: list) -> dict:
    """
    Match nodes from two FeoCategory trees using composite key priority:
      1. code (if both non-empty)
      2. (level, parent_path, normalized_name) — parent_path = tuple of normalized ancestor names
      3. (level, normalized_name) — fallback if parent renamed → marked as 'moved'

    Returns:
      {
        "matches": [(node_a, node_b, match_type)],  # match_type: 'code'|'path'|'fallback'
        "only_a": [node_a, ...],
        "only_b": [node_b, ...],
      }
    """
    def _flatten(tree, parent_path=()):
        nodes = []
        for node in tree:
            path = parent_path + (_normalize_name(node.get("name", "")),)
            nodes.append((node, path))
            nodes.extend(_flatten(node.get("children", []), path))
        return nodes

    flat_a = _flatten(tree_a)
    flat_b = _flatten(tree_b)

    matched_b = set()
    matched_a = set()
    matches = []

    # Pass 1: match by code
    code_map_b: dict[str, tuple] = {}
    for nb, pb in flat_b:
        code = (nb.get("code") or "").strip()
        if code:
            code_map_b[code] = (nb, pb)

    for na, pa in flat_a:
        code = (na.get("code") or "").strip()
        if code and code in code_map_b:
            nb, pb = code_map_b[code]
            id_b = id(nb)
            id_a = id(na)
            if id_b not in matched_b and id_a not in matched_a:
                matches.append((na, nb, "code"))
                matched_a.add(id_a)
                matched_b.add(id_b)

    # Pass 2: match by (level, parent_path, normalized_name)
    path_map_b: dict[tuple, tuple] = {}
    for nb, pb in flat_b:
        if id(nb) not in matched_b:
            key = (nb.get("level", 0), pb[:-1], _normalize_name(nb.get("name", "")))
            if key not in path_map_b:
                path_map_b[key] = (nb, pb)

    for na, pa in flat_a:
        if id(na) in matched_a:
            continue
        key = (na.get("level", 0), pa[:-1], _normalize_name(na.get("name", "")))
        if key in path_map_b:
            nb, pb = path_map_b[key]
            if id(nb) not in matched_b:
                matches.append((na, nb, "path"))
                matched_a.add(id(na))
                matched_b.add(id(nb))

    # Pass 3: fallback (level, normalized_name) — marks as 'fallback' → UI shows 'moved'
    name_level_map_b: dict[tuple, tuple] = {}
    for nb, pb in flat_b:
        if id(nb) not in matched_b:
            key = (nb.get("level", 0), _normalize_name(nb.get("name", "")))
            if key not in name_level_map_b:
                name_level_map_b[key] = (nb, pb)

    for na, pa in flat_a:
        if id(na) in matched_a:
            continue
        key = (na.get("level", 0), _normalize_name(na.get("name", "")))
        if key in name_level_map_b:
            nb, pb = name_level_map_b[key]
            if id(nb) not in matched_b:
                matches.append((na, nb, "fallback"))
                matched_a.add(id(na))
                matched_b.add(id(nb))

    only_a = [na for na, pa in flat_a if id(na) not in matched_a]
    only_b = [nb for nb, pb in flat_b if id(nb) not in matched_b]

    return {"matches": matches, "only_a": only_a, "only_b": only_b}
