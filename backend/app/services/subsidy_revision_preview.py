"""Предпросмотр корректировки — «было»/«станет» дерева ФЭО + баланс связок +
проблемы порога, без единой реальной записи в БД.

ПРАВИЛО №6: дерево считается ОДИН способ — compute_feo_plan_tree; узел
сериализуется В ТОМ ЖЕ ФОРМАТЕ, что отдаёт GET /api/feo-categories/plan-tree
(app.routers.feo_plan_reads_tree) — фронт сможет переиспользовать те же
компоненты отрисовки дерева для «после», просто подставив другой набор узлов.
"""
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_planned_item import FeoPlannedItem
from app.models.subsidy_revision import SubsidyRevision
from app.services.subsidy_revision_floor import check_floor, compute_balance

# Тот же список полей узла, что отдаёт GET /api/feo-categories/plan-tree (см.
# app/routers/feo_plan_reads_tree.py) — держим общий список здесь, чтобы
# "before"/"after" предпросмотра были теми же ключами, которые фронт уже умеет
# рисовать, не вторым форматом узла дерева.
NODE_FIELDS = (
    "plan_manual", "ordered_qty", "ordered_sum", "over", "over_quantity", "plan",
    "budget", "display", "residual", "forecast", "forecast_over", "consumed",
    "consumed_quantity", "qty_plan", "display_quantity", "committed",
    "committed_quantity", "fact", "fact_quantity", "plan_floor_added",
    "subsidy_id", "parent_id",
)


def _node_view(node: dict) -> dict:
    return {f: node.get(f) for f in NODE_FIELDS if f in node}


async def _items_view(db: AsyncSession, subsidy_id: int) -> dict:
    from sqlalchemy import select
    from app.models.feo_category import FeoCategory
    rows = (await db.execute(
        select(FeoPlannedItem).join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id, FeoPlannedItem.is_active.is_(True))
    )).scalars().all()
    return {
        it.id: {
            "id": it.id, "feo_category_id": it.feo_category_id, "name": it.name,
            "quantity": float(it.quantity) if it.quantity is not None else None,
            "unit": it.unit, "amount": float(it.amount) if it.amount is not None else None,
            "unit_price": float(it.unit_price) if it.unit_price is not None else None,
            "item_type": it.item_type,
        }
        for it in rows
    }


def _collect_touched_category_ids(ops: list) -> set:
    out = set()
    for op in ops:
        entity_type = op.entity_type if hasattr(op, "entity_type") else op.get("entity_type")
        if entity_type != "feo_category":
            continue
        target_id = op.target_id if hasattr(op, "target_id") else op.get("target_id")
        if target_id is not None:
            out.add(target_id)
    return out


def _ancestors_of(cat_id: int, by_id: dict) -> list:
    out = []
    cur = by_id.get(cat_id)
    while cur is not None and cur.get("parent_id") is not None:
        pid = cur["parent_id"]
        out.append(pid)
        cur = by_id.get(pid)
    return out


async def preview(
    db: AsyncSession, revision: SubsidyRevision,
    accepted_op_ids: Optional[list[int]] = None,
    reviewer_overrides: Optional[dict] = None,
    extra_ops: Optional[list[dict]] = None,
    include_before: bool = True,
) -> dict:
    """Возвращает {"before", "after", "changed", "ancestors", "bundles",
    "problems", "can_apply", "elapsed_ms"} — см. докстринг модуля/роутера.
    Ничего не пишет в БД (apply_ops внутри SAVEPOINT откатывается в finally).

    include_before=False (владелец, 02.10.2026, «предпросмотр занимал 1,7 с»)
    — «было» от правок корректировки не зависит, фронту нужно считать его
    ОДИН раз при открытии; при False ключ "before" возвращается {"nodes":
    None, "items": None, "totals": None} — ОБЕ тяжёлые операции (прямой
    compute_feo_plan_tree("было") и построение items_before/totals_before)
    пропускаются целиком. free_before для balance тогда берётся ОДНИМ живым
    вызовом subsidy_money_summary (её 'free' — та же формула budget−planned,
    см. её докстринг) — дешевле, чем полное дерево "было" плюс ещё один
    subsidy_money_summary внутри него самого (см. compute_balance docstring
    про двойной счёт дерева, когда он есть)."""
    from app.services.feo_plan_tree import compute_feo_plan_tree

    t0 = time.monotonic()
    subsidy_id = revision.subsidy_id

    tree_before: dict = {}
    items_before: Optional[dict] = None
    totals_before: Optional[dict] = None
    free_before_override: Optional[float] = None

    if include_before:
        tree_before = await compute_feo_plan_tree(db, [subsidy_id])
        items_before = await _items_view(db, subsidy_id)
        totals_before = {
            "plan_total": sum(n.get("display", 0.0) for n in tree_before.values() if n.get("parent_id") is None),
        }
        try:
            from app.services.subsidy_money_summary import subsidy_money_summary
            totals_before = (await subsidy_money_summary(db, [subsidy_id])).get(subsidy_id) or totals_before
            free_before_override = totals_before.get("free")
        except Exception:
            pass
    else:
        # ОДИН дешёвый живой вызов вместо полного дерева "было" — см. докстринг
        # функции выше.
        try:
            from app.services.subsidy_money_summary import subsidy_money_summary
            summary_before = (await subsidy_money_summary(db, [subsidy_id])).get(subsidy_id) or {}
            free_before_override = summary_before.get("free")
        except Exception:
            pass

    # Дерево/позиции "после" считаются ВНУТРИ SAVEPOINT (apply_ops не
    # коммитит; откат — в finally ниже) — нужно читать состояние ДО отката,
    # поэтому используется apply_ops напрямую, а не simulate() (та откатывает
    # сама и не отдаёт наружу промежуточное состояние).
    from app.services import subsidy_revision_ops as ops_svc
    from app.services.subsidy_revision_ops import load_ops
    from app.services.subsidy_revision_apply import apply_ops

    ops = await load_ops(db, revision.id)
    if accepted_op_ids is not None:
        accepted_set = set(accepted_op_ids)
        ops = [o for o in ops if o.id in accepted_set]
    full_ops = list(ops) + list(extra_ops or [])

    nested = await db.begin_nested()
    try:
        sim2 = await apply_ops(
            db, await ops_svc.revision_author_for(db, revision), subsidy_id, full_ops,
            reviewer_overrides=reviewer_overrides, source_ref=revision.id, create_version=False,
        )
        ref_map = sim2["ref_map"]
        problems = list(sim2["problems"])

        tree_after = await compute_feo_plan_tree(db, [subsidy_id])
        items_after = await _items_view(db, subsidy_id)
        totals_after = {
            "plan_total": sum(n.get("display", 0.0) for n in tree_after.values() if n.get("parent_id") is None),
        }
        money_summary_after: Optional[dict] = None
        try:
            from app.services.subsidy_money_summary import subsidy_money_summary
            money_summary_after = (await subsidy_money_summary(db, [subsidy_id])).get(subsidy_id)
            totals_after = money_summary_after or totals_after
        except Exception:
            pass

        problems += await check_floor(db, subsidy_id, full_ops, tree_after)
        # money_summary_after переиспользуется (ОДИН subsidy_money_summary на
        # "после", не два — см. докстринг compute_balance/preview) ;
        # free_before_override — живое число "до", посчитанное выше (один раз,
        # вместо полного дерева "до"+ещё одного summary внутри compute_balance).
        balance = await compute_balance(
            db, subsidy_id, full_ops, tree_before, tree_after,
            money_summary_after=money_summary_after, free_before_override=free_before_override,
        )
    finally:
        await nested.rollback()

    # Затронутые категории + их предки (для "раскрытых" веток дерева на фронте).
    by_id = {cid: {"parent_id": n.get("parent_id")} for cid, n in tree_after.items()}
    touched = _collect_touched_category_ids(full_ops)
    touched |= {v for k, v in ref_map.items() if k.startswith("c")}
    ancestors: set = set()
    for cid in touched:
        ancestors.update(_ancestors_of(cid, by_id))

    changed_categories = sorted(touched)
    changed_items = sorted({
        (op.target_id if hasattr(op, "target_id") else op.get("target_id"))
        for op in full_ops
        if (op.entity_type if hasattr(op, "entity_type") else op.get("entity_type")) == "feo_item"
        and (op.target_id if hasattr(op, "target_id") else op.get("target_id")) is not None
    } | {v for k, v in ref_map.items() if k.startswith("i")})

    can_apply = balance["can_apply"] and not problems

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    before_block = None
    if include_before:
        before_block = {
            "nodes": {cid: _node_view(n) for cid, n in tree_before.items()},
            "items": items_before,
            "totals": totals_before,
        }

    return {
        "before": before_block,
        "after": {
            "nodes": {cid: _node_view(n) for cid, n in tree_after.items()},
            "items": items_after,
            "totals": totals_after,
            "ref_map": ref_map,
        },
        "changed": {"categories": changed_categories, "items": changed_items},
        "ancestors": sorted(ancestors),
        "bundles": balance["bundles"],
        "balance": {k: v for k, v in balance.items() if k != "bundles"},
        "problems": problems,
        "can_apply": can_apply,
        "elapsed_ms": elapsed_ms,
    }

