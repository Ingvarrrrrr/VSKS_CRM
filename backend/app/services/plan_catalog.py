"""load_plan_catalog — вынесено из app/routers/feo_planned_items_matching.py
(ПРАВИЛО №5, рефакторинг 02.10.2026, без изменения поведения для имеющегося
потребителя — POST /feo-planned-items/match).

Добавлены quantity/unit_price/amount в каждую запись каталога (задача
подготовки импорта исторических закупок — нужны как кандидаты для
автосопоставления плановых сумм, не только имя/путь). Единственный
потребитель на момент выноса (_FeoMatchCandidate в
feo_planned_items_matching.py) читает конкретные ключи по имени
(entry["name"]/["path"]/...), новые ключи не читает и не ломается от их
наличия.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem


async def load_plan_catalog(db: AsyncSession, subsidy_id: int) -> list[dict]:
    """Каталог кандидатов для матчинга — тот же состав, что и в
    GET /feo-categories/plan-positions (единый источник «плановых позиций»,
    см. её докстринг): конечные категории ФЭО (лист дерева) с заполненным
    planned_quantity×planned_amount > 0 (kind='plan_position'|'feo_article'),
    плюс активные FeoPlannedItem этих листьев (kind='planned_item') — «может
    быть запланирована в ФЭО, а может только планово» (формулировка владельца).

    Не вызывает сам эндпоинт /plan-positions (тот считает ещё consumption/tree —
    не нужно для матчинга по имени), а строит облегчённую версию тех же строк:
    id/name/path/category_id/ancestor_ids/kind/quantity/unit_price/amount.
    path/ancestor_ids — те же хелперы
    app.services.feo_plan.build_category_path/build_ancestor_ids (read-only
    импорт, не дублируем).
    """
    from app.services.feo_plan import build_category_path, build_ancestor_ids

    all_cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    if not all_cats:
        return []

    cat_by_id = {c.id: c for c in all_cats}
    children_count: dict[int, int] = {}
    for c in all_cats:
        if c.parent_id is not None:
            children_count[c.parent_id] = children_count.get(c.parent_id, 0) + 1
    leaves = [c for c in all_cats if children_count.get(c.id, 0) == 0]

    catalog: list[dict] = []
    for c in leaves:
        qty = float(c.planned_quantity) if c.planned_quantity is not None else 0.0
        unit_price = float(c.planned_amount) if c.planned_amount is not None else 0.0
        if qty * unit_price <= 0:
            continue
        kind = "plan_position" if (c.budget is None and c.feo_amount is None) else "feo_article"
        catalog.append({
            "id": c.id,
            "name": c.name or "",
            "path": build_category_path(c, cat_by_id),
            "category_id": c.id,
            "ancestor_ids": build_ancestor_ids(c, cat_by_id),
            "kind": kind,
            "quantity": qty,
            "unit_price": unit_price,
            "amount": qty * unit_price,
        })

    if leaves:
        fpi_rows = (await db.execute(
            select(FeoPlannedItem)
            .where(FeoPlannedItem.feo_category_id.in_([c.id for c in leaves]))
            .where(FeoPlannedItem.is_active == True)
        )).scalars().all()
        for it in fpi_rows:
            cat = cat_by_id.get(it.feo_category_id)
            _it_qty = float(it.quantity) if it.quantity is not None else None
            _it_unit_price = float(it.unit_price) if it.unit_price is not None else None
            _it_amount = float(it.amount) if it.amount is not None else None
            catalog.append({
                "id": it.id,
                "name": it.name or "",
                "path": build_category_path(cat, cat_by_id) if cat else "",
                "category_id": it.feo_category_id,
                "ancestor_ids": build_ancestor_ids(cat, cat_by_id) if cat else [],
                "kind": "planned_item",
                "quantity": _it_qty,
                "unit_price": _it_unit_price,
                "amount": _it_amount,
            })

    return catalog
