"""Операции над деревом категорий ФЭО: перенос узла, изменение порядка,
приравнивание ФЭО к плану.

Разрезано из app/routers/feo_categories.py (Правило №5, модульность) без
изменения поведения. Все три пути имеют вид "/{cat_id}/<literal>" — длиннее
catch-all "/{cat_id}" ядра как минимум на один сегмент, поэтому порядок
регистрации относительно feo_categories.router не важен (тот же принцип, что
и у wish_transitions.router относительно wishes.router) — регистрируется
рядом с ним в app/routes.py для читаемости.

Гейт записи и обход поддерева зовутся через `from app.routers import
feo_categories as fc` — так monkeypatch `fc._require_feo_category_write` в
тестах (test_feo_category_write_gate.py, вызывает `fc.move_category(...)` и
`fc.reorder_category(...)` напрямую — см. `__getattr__` в feo_categories.py)
продолжает работать независимо от того, что реальный код теперь здесь.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.feo_category import FeoCategory
from app.auth.jwt import require_role, ADMIN_ROLES
from app.auth.permissions import require_tab
from app.routers import feo_categories as fc

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


@router.patch("/{cat_id}/move")
async def move_category(
    cat_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Move category to a new parent. Set parent_id=null to make root."""
    cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    # B2: субсидия перемещаемой категории — из объекта, загруженного из БД (move
    # запрещает менять субсидию, см. проверку ниже "Нельзя переместить в другую
    # субсидию" — cat.subsidy_id остаётся тем же и после перемещения).
    await fc._require_feo_category_write(current_user, db, cat.subsidy_id)

    new_parent_id = data.get("parent_id")
    warning = None

    # Determine new level
    if new_parent_id:
        parent = (await db.execute(select(FeoCategory).where(FeoCategory.id == new_parent_id))).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Родительская категория не найдена")
        if parent.subsidy_id != cat.subsidy_id:
            raise HTTPException(status_code=400, detail="Нельзя переместить в другую субсидию")
        new_level = parent.level + 1
    else:
        new_level = 1

    level_delta = new_level - cat.level

    # Check for circular reference
    if new_parent_id:
        subtree_ids = await fc._collect_subtree_ids(cat_id, db)
        if new_parent_id in subtree_ids:
            raise HTTPException(status_code=400, detail="Нельзя переместить в собственное поддерево")

    # Check if new max depth creates a previously unseen level
    max_child_depth = 0
    all_ids = await fc._collect_subtree_ids(cat_id, db)
    if len(all_ids) > 1:
        max_existing = (await db.execute(
            select(func.max(FeoCategory.level)).where(FeoCategory.id.in_(all_ids))
        )).scalar() or cat.level
        max_child_depth = max_existing - cat.level
    new_max_level = new_level + max_child_depth
    existing_max = (await db.execute(
        select(func.max(FeoCategory.level)).where(FeoCategory.subsidy_id == cat.subsidy_id)
    )).scalar() or 1
    if new_max_level > existing_max:
        warning = f"Создан новый уровень вложенности: {new_max_level}"

    # Update category
    cat.parent_id = new_parent_id
    cat.level = new_level

    # Recursively update children levels
    if level_delta != 0:
        await _update_subtree_levels(cat_id, level_delta, db)

    await db.commit()
    result = {"ok": True, "new_level": new_level}
    if warning:
        result["warning"] = warning
    return result


@router.patch("/{cat_id}/reorder")
async def reorder_category(
    cat_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Move a category up/down among its siblings (same parent, same subsidy).
    Body: {"direction": "up"|"down"}. Swaps sort_order with the adjacent sibling."""
    direction = (data.get("direction") or "").lower()
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="direction должен быть 'up' или 'down'")
    cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    # B2: субсидия — из объекта, загруженного из БД (тело содержит только direction).
    await fc._require_feo_category_write(current_user, db, cat.subsidy_id)
    sib_filter = (
        FeoCategory.parent_id.is_(None) if cat.parent_id is None
        else FeoCategory.parent_id == cat.parent_id
    )
    siblings = (await db.execute(
        select(FeoCategory)
        .where(FeoCategory.subsidy_id == cat.subsidy_id, sib_filter)
        .order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    )).scalars().all()
    # Normalize any NULL sort_order to a stable increasing sequence
    for i, s in enumerate(siblings):
        if s.sort_order is None:
            s.sort_order = (i + 1) * 10
    idx = next((i for i, s in enumerate(siblings) if s.id == cat_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Категория не найдена среди соседей")
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if swap_idx < 0 or swap_idx >= len(siblings):
        await db.commit()
        return {"ok": True, "moved": False}
    a, b = siblings[idx], siblings[swap_idx]
    a.sort_order, b.sort_order = b.sort_order, a.sort_order
    await db.commit()
    return {"ok": True, "moved": True}


@router.post("/{cat_id}/align-budget-to-plan")
async def align_budget_to_plan(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(*ADMIN_ROLES)),
):
    """«Приравнять ФЭО к сумме плана» — задача владельца (2026-08-12): «должна быть
    кнопка, которая приравнивает сумму ФЭО к сумме плана — условно в конце, когда
    подбивают итоги; это может сделать только админ организации, не ниже».

    Права: require_role(*ADMIN_ROLES) — ADMIN_ROLES = (superadmin, account_owner,
    admin, org_admin), см. app.auth.jwt — org_admin и выше, org_admin включён
    ЯВНО (в подобных кортежах ролей в проекте раньше терялся именно он).

    Целевое значение budget = node["plan"] + node["over"] — ПОЛНАЯ плановая сумма
    узла (см. app.services.feo_plan.compute_feo_plan_tree._visit: full_display),
    а НЕ node["display"]. display может быть уже искусственно занижен до
    plan_manual, если по узлу висит несогласованное превышение плана над ФЭО
    (excess_amount>0 и не excess_approved) — использовать урезанный display
    означало бы занизить итоговое ФЭО и молча оставить расхождение вместо того,
    чтобы его устранить. plan+over — это РЕАЛЬНАЯ сумма того, что запланировано/
    заказано по узлу целиком, именно её и нужно «подбить» в ФЭО при закрытии
    итогов.

    Обязана уважать жёсткий потолок субсидии (задача владельца п.3, см.
    app.services.feo_plan.assert_no_unapproved_excess) — если ПОСЛЕ приравнивания
    суммарный план по субсидии окажется больше суммарного финансирования по ФЭО
    (calculate_budget_from_categories), budget откатывается и действие отклоняется
    с цифрами. Это тот же потолок, что не согласуется НИ ПРИ КАКИХ обстоятельствах —
    у align-budget-to-plan для него тоже нет обхода.

    Response: {id, name, subsidy_id, old_budget, new_budget}. В проекте нет
    отдельного механизма истории/audit-лога для feo_categories (проверено —
    BudgetHistory существует, но её entity_type жёстко "subsidy"/"purchase", для
    категорий ФЭО не заводился и заводить его тут не стали, чтобы не путать
    существующих потребителей этой таблицы) — только before/after в этом ответе.
    """
    from app.services.feo_plan import compute_feo_plan_tree
    from app.routers.subsidies import calculate_budget_from_categories

    cat = await db.get(FeoCategory, cat_id)
    if cat is None:
        raise HTTPException(404, "Категория ФЭО не найдена")
    if not cat.subsidy_id:
        raise HTTPException(422, "У категории не задана субсидия")

    tree = await compute_feo_plan_tree(db, [cat.subsidy_id])
    node = tree.get(cat_id)
    if node is None:
        raise HTTPException(404, "Узел ФЭО не найден в дереве плана")

    old_budget = float(cat.budget) if cat.budget is not None else None
    new_budget = Decimal(str(node["plan"] + node["over"])).quantize(Decimal("0.01"))

    cat.budget = new_budget
    await db.flush()

    # Пересчитать дерево/потолок УЖЕ с новым budget — изменение budget само влияет
    # и на display/excess_amount узла, и на общий потолок финансирования субсидии
    # (см. app.routers.subsidies.calculate_budget_from_categories).
    tree_after = await compute_feo_plan_tree(db, [cat.subsidy_id])
    total_plan_after = sum(n["display"] for n in tree_after.values() if n["parent_id"] is None)
    ceiling_after = await calculate_budget_from_categories(db, cat.subsidy_id)

    if ceiling_after and ceiling_after > 0:
        total_plan_after_d = Decimal(str(total_plan_after))
        ceiling_after_d = Decimal(str(ceiling_after))
        if total_plan_after_d - ceiling_after_d > Decimal("0.005"):
            over_d = total_plan_after_d - ceiling_after_d
            await db.rollback()
            raise HTTPException(
                409,
                {
                    "code": "PLAN_OVER_SUBSIDY_CEILING",
                    "message": (
                        f"Приравнять ФЭО к плану нельзя: после этого суммарный план по субсидии "
                        f"составит {total_plan_after_d:,.2f} ₽, а общий потолок финансирования по "
                        f"ФЭО — {ceiling_after_d:,.2f} ₽ (превышение {over_d:,.2f} ₽). Уменьшите "
                        f"финансирование или план по другим категориям субсидии."
                    ),
                    "subsidy_id": cat.subsidy_id,
                    "total_plan": float(total_plan_after_d),
                    "ceiling": float(ceiling_after_d),
                    "over_amount": float(over_d),
                },
            )

    await db.commit()
    await db.refresh(cat)

    return {
        "id": cat.id,
        "name": cat.name,
        "subsidy_id": cat.subsidy_id,
        "old_budget": old_budget,
        "new_budget": float(cat.budget),
    }


async def _update_subtree_levels(cat_id: int, level_delta: int, db: AsyncSession):
    """Recursively update levels of all children by delta."""
    children = (await db.execute(
        select(FeoCategory).where(FeoCategory.parent_id == cat_id)
    )).scalars().all()
    for child in children:
        child.level = child.level + level_delta
        await _update_subtree_levels(child.id, level_delta, db)
