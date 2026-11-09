"""subsidy_ceiling_diff.py — снимок и контроль ухудшения потолка субсидии.

Вынесено из subsidy_ceiling.py по Правилу №5 (модульность) по задаче
владельца 09.11.2026 (ложный 409 на закупке 4882 при подорожании позиции внутри
своей плановой строки).
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.feo_plan_tree import compute_feo_plan_tree


async def ceiling_snapshot(db: AsyncSession, subsidy_id: int) -> dict:
    """Снимок состояния потолка субсидии — {ceiling, total_plan, per_cat: {cat_id: plan+over узла дерева}}.
    Владелец 09.11.2026, ложный 409 на закупке 4882."""
    from app.services.subsidy_budget import feo_entered_ceiling_and_plan

    tree = await compute_feo_plan_tree(db, [subsidy_id])
    ceiling, total_plan, entered_node_ids = await feo_entered_ceiling_and_plan(db, subsidy_id, tree)

    # Категории — листовые узлы (узлы без детей в дереве), чтобы не дублировать родителей
    parent_ids = {node.get("parent_id") for node in tree.values() if node.get("parent_id") is not None}
    per_cat = {}
    for cid, node in tree.items():
        if cid not in parent_ids:
            plan_val = float(node.get("plan", 0.0) or 0.0)
            over_val = float(node.get("over", 0.0) or 0.0)
            per_cat[cid] = plan_val + over_val

    return {
        "subsidy_id": subsidy_id,
        "ceiling": float(ceiling or 0.0),
        "total_plan": float(total_plan or 0.0),
        "per_cat": per_cat,
    }


async def assert_ceiling_not_worsened(db: AsyncSession, subsidy_id: int, before: dict) -> None:
    """Пересчитать снимок ПОСЛЕ изменений (сначала await db.flush()), блокировать
    409 PLAN_OVER_SUBSIDY_CEILING ТОЛЬКО если after.total_plan > ceiling + 0.005 И after.total_plan > before.total_plan + 0.005.
    Иначе пропустить (нейтральные/уменьшающие правки, подорожание в пределах плановой строки, перенос между категориями).
    Владелец 09.11.2026, ложный 409 на закупке 4882."""
    await db.flush()
    from app.services.feo_plan_tree_cache import invalidate_tree_cache
    invalidate_tree_cache([subsidy_id])

    after = await ceiling_snapshot(db, subsidy_id)

    total_plan_after_d = Decimal(str(after["total_plan"]))
    ceiling_d = Decimal(str(after["ceiling"]))
    plan_before_d = Decimal(str(before.get("total_plan", 0.0)))

    # Блокировать ТОЛЬКО если after.total_plan > ceiling + 0.005 И after.total_plan > before.total_plan + 0.005
    if not (total_plan_after_d > ceiling_d + Decimal("0.005") and total_plan_after_d > plan_before_d + Decimal("0.005")):
        return

    growth_d = total_plan_after_d - plan_before_d
    over_d = total_plan_after_d - ceiling_d

    # Рост по категориям
    before_per_cat = before.get("per_cat", {})
    after_per_cat = after.get("per_cat", {})

    growing_cats: list[dict] = []
    all_cat_ids = set(after_per_cat) | set(before_per_cat)
    for cid in all_cat_ids:
        amt_after = after_per_cat.get(cid, 0.0)
        amt_before = before_per_cat.get(cid, 0.0)
        delta = Decimal(str(amt_after)) - Decimal(str(amt_before))
        if delta > Decimal("0.005"):
            growing_cats.append({"category_id": cid, "delta": delta})

    growing_cats.sort(key=lambda x: x["delta"], reverse=True)
    top_growing = growing_cats[:10]

    growth_by_category = []
    if top_growing:
        from app.models.feo_category import FeoCategory
        from sqlalchemy import select
        cat_ids = [c["category_id"] for c in top_growing]
        c_res = await db.execute(select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(cat_ids)))
        c_rows = c_res.all()
        name_map = {r[0]: r[1] for r in c_rows}
        for item in top_growing:
            cid = item["category_id"]
            delta = item["delta"]
            cat_name = name_map.get(cid) or f"#{cid}"
            growth_by_category.append({
                "category_id": cid,
                "name": cat_name,
                "delta": float(delta),
            })

    from app.services.documents.formatting import _fmt_money as _fmt_rub_num
    from app.models.subsidy import Subsidy

    subsidy_row = await db.get(Subsidy, subsidy_id)
    subsidy_name = subsidy_row.name if subsidy_row else f"#{subsidy_id}"

    cats_str_parts = [
        f"«{g['name']}» +{_fmt_rub_num(Decimal(str(g['delta'])))} ₽"
        for g in growth_by_category
    ]
    if cats_str_parts:
        cats_str = " Рост плана дают категории: " + "; ".join(cats_str_parts) + "."
    else:
        cats_str = ""

    message = (
        f"Жёсткий потолок ФЭО по субсидии «{subsidy_name}»: план до сохранения "
        f"{_fmt_rub_num(plan_before_d)} ₽, после — {_fmt_rub_num(total_plan_after_d)} ₽ "
        f"(рост {_fmt_rub_num(growth_d)} ₽), потолок {_fmt_rub_num(ceiling_d)} ₽, "
        f"превышение {_fmt_rub_num(over_d)} ₽.{cats_str} Ограничение не согласуется — "
        f"уменьшите план минимум на {_fmt_rub_num(over_d)} ₽."
    )

    raise HTTPException(
        409,
        {
            "code": "PLAN_OVER_SUBSIDY_CEILING",
            "message": message,
            "subsidy_id": subsidy_id,
            "total_plan": float(total_plan_after_d),
            "ceiling": float(ceiling_d),
            "over_amount": float(over_d),
            "plan_before": float(plan_before_d),
            "growth": float(growth_d),
            "growth_by_category": growth_by_category,
        },
    )
