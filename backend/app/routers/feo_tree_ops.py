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
from app.services import feo_history
from app.services import feo_tree_write

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])

# Второй роутер в этом же файле (не второй модуль — Правило №5 про разрезание
# относится к РАЗНЫМ ответственностям, а не к одному эндпоинту «приравнять»,
# который просто живёт под другим префиксом пути, /api/subsidies вместо
# /api/feo-categories): align-budget-to-plan-all — субсидийная версия
# align-budget-to-plan выше (та же логика, ОДИН вызов на всю субсидию, см.
# app.services.feo_tree_write.align_budget_to_plan_all), решение владельца
# 07.10.2026, план .planning/quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 3.
router_subsidy_feo = APIRouter(prefix="/api/subsidies", tags=["subsidies"])


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
    from app.services.subsidy_revision_guard import assert_direct_edit
    await assert_direct_edit(db, current_user, cat.subsidy_id)

    new_parent_id = data.get("parent_id")
    result = await feo_tree_write.move_category(db, current_user, cat, new_parent_id)
    await db.commit()
    out = {"ok": True, "new_level": result["new_level"]}
    if result["warning"]:
        out["warning"] = result["warning"]
    return out


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
    from app.services.subsidy_revision_guard import assert_direct_edit
    await assert_direct_edit(db, current_user, cat.subsidy_id)

    result = await feo_tree_write.reorder_category(db, cat, direction)
    await db.commit()
    return {"ok": True, "moved": result["moved"]}


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
    app.services.feo_plan.assert_no_unapproved_excess) — НО не тупиковым образом.
    Боевой случай (субсидия ДНР_2026, 22.09): у субсидии план УЖЕ выше потолка
    ФЭО (одна категория с ручным ФЭО ниже своего плана, другая — вовсе без ФЭО).
    Владелец жмёт «Приравнять» на категории без ФЭО — превышение субсидии
    ПАДАЕТ (действие подтягивает финансирование туда, где его не хватало), но
    старая проверка «план после > потолок после» всё равно отказывала 409,
    потому что сравнивала с абсолютным нулём, а не с тем, что было ДО. На такой
    субсидии ни одну категорию без ФЭО было не приравнять — тупик.
    Фикс: считаем превышение субсидии ДО (total_plan_before − ceiling_before, по
    тому же дереву/потолку, ДО изменения budget) и ПОСЛЕ — отказываем 409 ТОЛЬКО
    если превышение ПОСЛЕ больше превышения ДО (действие ухудшает субсидию, а
    не просто существует остаточное превышение). Тот же calculate_budget_from_
    categories/compute_feo_plan_tree, вызванные дважды (до/после) — не второй
    расчёт, тот же самый.

    Response (200): {id, name, subsidy_id, old_budget, new_budget,
    subsidy_over_before, subsidy_over_after} — последние два поля дают фронту
    показать «превышение по субсидии уменьшилось с … до …». В проекте нет
    отдельного механизма истории/audit-лога для feo_categories (проверено —
    BudgetHistory существует, но её entity_type жёстко "subsidy"/"purchase", для
    категорий ФЭО не заводился и заводить его тут не стали, чтобы не путать
    существующих потребителей этой таблицы) — только before/after в этом ответе.
    """
    cat = await db.get(FeoCategory, cat_id)
    if cat is None:
        raise HTTPException(404, "Категория ФЭО не найдена")
    if not cat.subsidy_id:
        raise HTTPException(422, "У категории не задана субсидия")
    from app.services.subsidy_revision_guard import assert_direct_edit
    await assert_direct_edit(db, current_user, cat.subsidy_id)

    result = await feo_tree_write.align_budget_to_plan(db, current_user, cat)
    await db.commit()
    await db.refresh(cat)

    return {
        "id": cat.id,
        "name": cat.name,
        "subsidy_id": cat.subsidy_id,
        "old_budget": result["old_budget"],
        "new_budget": result["new_budget"],
        "subsidy_over_before": result["subsidy_over_before"],
        "subsidy_over_after": result["subsidy_over_after"],
    }


@router_subsidy_feo.post("/{subsidy_id}/feo/align-budget-to-plan-all")
async def align_budget_to_plan_all(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(*ADMIN_ROLES)),
):
    """«Приравнять ФЭО к плану по всем статьям» одним действием (решение
    владельца 07.10.2026, план .planning/quick/2026-10-07-dnr-feo-cards/
    PLAN.md шаг 3, решение владельца №4 — кнопка в шапке дерева ФЭО). Права —
    ТЕ ЖЕ, что у одиночного POST /api/feo-categories/{cat_id}/align-budget-
    to-plan (require_role(*ADMIN_ROLES) — org_admin и выше).

    budget := plan+over у КАЖДОЙ категории субсидии сразу (см. docstring
    app.services.feo_tree_write.align_budget_to_plan_all — внутри вызывается
    ТО ЖЕ целевое значение, что и одиночное действие, не вторая формула;
    потолочная проверка здесь не нужна — после действия budget==plan везде,
    превышение субсидии равно нулю по построению).

    Response (200): {subsidy_id, count (сколько статей изменено), total
    (Σ ФЭО по всей субсидии после действия)}."""
    from app.models.subsidy import Subsidy
    subsidy = await db.get(Subsidy, subsidy_id)
    if subsidy is None:
        raise HTTPException(404, "Субсидия не найдена")
    from app.services.subsidy_revision_guard import assert_direct_edit
    await assert_direct_edit(db, current_user, subsidy_id)

    result = await feo_tree_write.align_budget_to_plan_all(db, current_user, subsidy_id)
    await db.commit()
    return {"subsidy_id": subsidy_id, "count": result["count"], "total": result["total"]}


# Алиас на прежнее имя — feo_categories.py лениво ре-экспортирует
# `_update_subtree_levels` отсюда (см. её __getattr__/_LAZY_REEXPORTS), сама
# реализация переехала в app.services.feo_tree_write (Правило №5/№6).
_update_subtree_levels = feo_tree_write.update_subtree_levels
