"""feo_order_diff.py — строки окна «Перерасход/экономия по заказам» (владелец,
13.10.2026, правка после замечания координатора: «перерасход/экономия
считаются ПО ПОЗИЦИИ, не по сумме категории» — боевой пример «Форменная
одежда», где экономия «Шапки» гасила перерасход «Повседневного костюма» в
сетевой сумме узла).

ЕДИНАЯ точка (ПРАВИЛО №6) — поверх committed_amounts.planned_item_order_diffs,
ТОЙ ЖЕ функции, которую compute_feo_plan_tree (feo_plan_tree.py) суммирует в
order_overspend/order_economy узла. Суммы этого модуля (overspend_total/
economy_total) ОБЯЗАНЫ совпадать с Σ order_overspend/order_economy корневых
узлов дерева субсидии (см. test_feo_order_diff_rows.py) — второй формулы
здесь нет, только построение строк (путь категории, позиция, план из файла,
сумма по договору, разница, привязанные закупки) поверх уже готовых diff'ов.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.services.committed_amounts import planned_item_order_diffs

_PURCHASE_CONTRACT_FIELDS = (
    "id", "registry_number", "purchase_number", "status", "status_label",
    "amount", "stopped_at",
)


def _category_descendants(parent_by_id: dict[int, Optional[int]], root_id: int) -> set[int]:
    """root_id + все его потомки (любой глубины) — для фильтра «строки только
    этой категории и её поддерева» (клик по категории дерева)."""
    result = {root_id}
    changed = True
    while changed:
        changed = False
        for cid, pid in parent_by_id.items():
            if pid in result and cid not in result:
                result.add(cid)
                changed = True
    return result


async def order_substitution_rows(
    db: AsyncSession, subsidy_id: int, category_id: Optional[int] = None,
) -> dict:
    """{"overspend": [...], "economy": [...], "overspend_total": float,
    "economy_total": float} — строки отсортированы по |diff| по убыванию
    (владелец: «сортировка по модулю разницы»). category_id — опциональный
    фильтр: только эта категория + её поддерево (клик по подписи категории,
    FeoCategoryEconomyNote.vue); без него — вся субсидия (клик по карточке
    «Запланировано», SubsidyKpiCards.vue)."""
    cat_rows = (
        await db.execute(
            select(FeoCategory.id, FeoCategory.name, FeoCategory.parent_id)
            .where(FeoCategory.subsidy_id == subsidy_id)
        )
    ).all()
    name_by_id = {r.id: r.name for r in cat_rows}
    parent_by_id: dict[int, Optional[int]] = {r.id: r.parent_id for r in cat_rows}
    all_cat_ids = list(name_by_id.keys())

    def _path(cid: int) -> str:
        parts: list[str] = []
        cur: Optional[int] = cid
        seen: set = set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            parts.append(name_by_id.get(cur, f"#{cur}"))
            cur = parent_by_id.get(cur)
        return " / ".join(reversed(parts))

    diffs = await planned_item_order_diffs(db, all_cat_ids)

    if category_id is not None:
        allowed_cat_ids = _category_descendants(parent_by_id, category_id)
        diffs = {iid: info for iid, info in diffs.items() if info["feo_category_id"] in allowed_cat_ids}

    item_ids = list(diffs.keys())
    purchases_by_item: dict[int, list[dict]] = {}
    if item_ids:
        from app.services.feo_plan_fact import planned_item_consumption
        from app.services.purchase_summary import purchase_summaries_by_id

        consumption = await planned_item_consumption(db, item_ids)
        purchase_ids_needed: set = set()
        for c in consumption.values():
            purchase_ids_needed.update(c.get("linked_purchase_ids") or [])
        summaries = await purchase_summaries_by_id(db, purchase_ids_needed) if purchase_ids_needed else {}
        for item_id, c in consumption.items():
            linked = c.get("linked_purchase_ids") or []
            purchases_by_item[item_id] = [
                {k: summaries[pid][k] for k in _PURCHASE_CONTRACT_FIELDS}
                for pid in linked if pid in summaries
            ]

    overspend_rows: list[dict] = []
    economy_rows: list[dict] = []
    overspend_total = 0.0
    economy_total = 0.0
    for item_id, info in diffs.items():
        diff = info["diff"]
        if abs(diff) <= 0.005:
            continue
        row = {
            "feo_item_id": item_id,
            "category_id": info["feo_category_id"],
            "category_path": _path(info["feo_category_id"]),
            "name": info["name"],
            "plan_from_file": info["amount"],
            "contract_amount": info["contribution"],
            "diff": diff,
            "purchases": purchases_by_item.get(item_id, []),
        }
        if diff > 0:
            overspend_rows.append(row)
            overspend_total += diff
        else:
            economy_rows.append(row)
            economy_total += -diff

    overspend_rows.sort(key=lambda r: -abs(r["diff"]))
    economy_rows.sort(key=lambda r: -abs(r["diff"]))

    return {
        "overspend": overspend_rows,
        "economy": economy_rows,
        "overspend_total": overspend_total,
        "economy_total": economy_total,
    }
