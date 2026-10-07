"""Запись операций над ФОРМОЙ дерева категорий ФЭО: перенос узла (move),
изменение порядка (reorder), приравнивание ФЭО к плану (align-budget-to-plan).

Сестра app/services/feo_category_write.py (create/update/delete) — то же
разрезание app/routers/feo_tree_ops.py (Правило №5) и тот же мотив (Правило
№6): применение будущей корректировки субсидии после утверждения обязано
пройти ТЕ ЖЕ действия, что и прямая правка через эти ручки, значит код
действия не может жить только внутри HTTP-обработчика.

Контракт — тот же, что и у feo_category_write.py: принимают db/user/уже
загруженный объект, НЕ коммитят, НЕ проверяют права.
"""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.services import feo_history


async def update_subtree_levels(cat_id: int, level_delta: int, db: AsyncSession):
    """Recursively update levels of all children by delta."""
    children = (await db.execute(
        select(FeoCategory).where(FeoCategory.parent_id == cat_id)
    )).scalars().all()
    for child in children:
        child.level = child.level + level_delta
        await update_subtree_levels(child.id, level_delta, db)


async def move_category(
    db: AsyncSession, user, cat: FeoCategory, new_parent_id: Optional[int],
    *, source: str = feo_history.SOURCE_MANUAL, source_ref: Optional[int] = None,
) -> dict:
    """Тело PATCH /feo-categories/{cat_id}/move (без гейта прав, без коммита).
    Move category to a new parent. Set parent_id=None to make root.
    Возвращает {"new_level": int, "warning": Optional[str]}.
    """
    from app.routers.feo_categories import _collect_subtree_ids

    warning = None

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

    if new_parent_id:
        subtree_ids = await _collect_subtree_ids(cat.id, db)
        if new_parent_id in subtree_ids:
            raise HTTPException(status_code=400, detail="Нельзя переместить в собственное поддерево")

    max_child_depth = 0
    all_ids = await _collect_subtree_ids(cat.id, db)
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

    _old_parent_id, _old_level = cat.parent_id, cat.level
    cat.parent_id = new_parent_id
    cat.level = new_level

    if level_delta != 0:
        await update_subtree_levels(cat.id, level_delta, db)

    if _old_parent_id != new_parent_id:
        await feo_history.record_updated(
            db, feo_history.ENTITY_FEO_CATEGORY, cat.id, user,
            {"parent_id": _old_parent_id, "level": _old_level},
            {"parent_id": new_parent_id, "level": new_level},
            source=source, source_ref=source_ref, commit=False,
        )

    return {"new_level": new_level, "warning": warning}


async def reorder_category(db: AsyncSession, cat: FeoCategory, direction: str) -> dict:
    """Тело PATCH /feo-categories/{cat_id}/reorder (без гейта прав, без
    коммита). direction: 'up'|'down'. Возвращает {"moved": bool}."""
    sib_filter = (
        FeoCategory.parent_id.is_(None) if cat.parent_id is None
        else FeoCategory.parent_id == cat.parent_id
    )
    siblings = (await db.execute(
        select(FeoCategory)
        .where(FeoCategory.subsidy_id == cat.subsidy_id, sib_filter)
        .order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    )).scalars().all()
    for i, s in enumerate(siblings):
        if s.sort_order is None:
            s.sort_order = (i + 1) * 10
    idx = next((i for i, s in enumerate(siblings) if s.id == cat.id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Категория не найдена среди соседей")
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if swap_idx < 0 or swap_idx >= len(siblings):
        return {"moved": False}
    a, b = siblings[idx], siblings[swap_idx]
    a.sort_order, b.sort_order = b.sort_order, a.sort_order
    return {"moved": True}


async def align_budget_to_plan(
    db: AsyncSession, user, cat: FeoCategory,
    *, source: str = feo_history.SOURCE_MANUAL, source_ref: Optional[int] = None,
) -> dict:
    """Тело POST /feo-categories/{cat_id}/align-budget-to-plan (без гейта
    прав, без коммита). «Приравнять ФЭО к сумме плана» — задача владельца
    (2026-08-12), см. полный докстринг действия в истории роутера до
    разрезания (routers/feo_tree_ops.py) — поведение и формулы не менялись,
    перенесено как есть:

    budget := node["plan"] + node["over"] (ПОЛНАЯ плановая сумма узла, не
    урезанный display). Жёсткий потолок субсидии уважается НЕ тупиковым
    образом — отказ 409 только если превышение субсидии ПОСЛЕ действия
    становится БОЛЬШЕ, чем было ДО (а не просто «осталось больше нуля»).

    Возвращает {"old_budget", "new_budget", "subsidy_over_before",
    "subsidy_over_after"}.
    """
    from app.services.feo_plan import compute_feo_plan_tree
    # ОДНА функция для (ceiling, total_plan), общая с feo_plan_excess.py
    # жёстким потолком — см. её докстринг (Правило №6, решение владельца
    # 07.10.2026, план .planning/quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 3):
    # статьи без ФЭО во всём поддереве не участвуют ни в plan, ни в ceiling.
    from app.services.subsidy_budget import feo_entered_ceiling_and_plan
    # Суммы в тексте 409 — по-русски (пробел тысяч, запятая дробная), ТОТ ЖЕ
    # хелпер, что и документы (Правило №6, не вторая копия форматирования).
    from app.services.documents.formatting import _fmt_money as _fmt_rub_num

    if not cat.subsidy_id:
        raise HTTPException(422, "У категории не задана субсидия")

    tree = await compute_feo_plan_tree(db, [cat.subsidy_id])
    node = tree.get(cat.id)
    if node is None:
        raise HTTPException(404, "Узел ФЭО не найден в дереве плана")

    old_budget = float(cat.budget) if cat.budget is not None else None
    new_budget = Decimal(str(node["plan"] + node["over"])).quantize(Decimal("0.01"))

    ceiling_before, total_plan_before, _ = await feo_entered_ceiling_and_plan(db, cat.subsidy_id, tree)
    total_plan_before_d = Decimal(str(total_plan_before))
    ceiling_before_d = Decimal(str(ceiling_before)) if ceiling_before else Decimal("0")
    over_before_d = (
        max(total_plan_before_d - ceiling_before_d, Decimal("0"))
        if ceiling_before_d > 0 else Decimal("0")
    )

    cat.budget = new_budget
    await db.flush()

    tree_after = await compute_feo_plan_tree(db, [cat.subsidy_id])
    ceiling_after, total_plan_after, _ = await feo_entered_ceiling_and_plan(db, cat.subsidy_id, tree_after)
    total_plan_after_d = Decimal(str(total_plan_after))
    ceiling_after_d = Decimal(str(ceiling_after)) if ceiling_after else Decimal("0")
    over_after_d = (
        max(total_plan_after_d - ceiling_after_d, Decimal("0"))
        if ceiling_after_d > 0 else Decimal("0")
    )

    if ceiling_after_d > 0 and (over_after_d - over_before_d) > Decimal("0.005"):
        root_ids = [cid for cid, n in tree_after.items() if n["parent_id"] is None]
        name_rows = (await db.execute(
            select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(root_ids))
        )).all()
        name_by_id = {r.id: r.name for r in name_rows}
        over_root_lines = []
        for rid in root_ids:
            rn = tree_after[rid]
            disp_d = Decimal(str(rn["display"]))
            rb = rn["budget"]
            rname = name_by_id.get(rid, str(rid))
            if rb is None:
                if disp_d > Decimal("0.005"):
                    over_root_lines.append(f"{rname}: план {_fmt_rub_num(disp_d)} ₽ / ФЭО не задано")
            else:
                rb_d = Decimal(str(rb))
                if disp_d - rb_d > Decimal("0.005"):
                    over_root_lines.append(f"{rname}: план {_fmt_rub_num(disp_d)} ₽ / ФЭО {_fmt_rub_num(rb_d)} ₽")

        # Читаем subsidy_id ДО rollback — после db.rollback() объект `cat`
        # expired (см. прежний докстринг до разрезания про MissingGreenlet).
        subsidy_id_for_error = cat.subsidy_id
        await db.rollback()
        over_d = over_after_d - over_before_d
        _lines_suffix = ("; " + "; ".join(over_root_lines)) if over_root_lines else ""
        raise HTTPException(
            409,
            {
                "code": "PLAN_OVER_SUBSIDY_CEILING",
                "message": (
                    f"Приравнять ФЭО к плану нельзя: после этого превышение плана над потолком "
                    f"финансирования по субсидии вырастет с {_fmt_rub_num(over_before_d)} ₽ до "
                    f"{_fmt_rub_num(over_after_d)} ₽ (суммарный план составит {_fmt_rub_num(total_plan_after_d)} ₽, "
                    f"потолок ФЭО — {_fmt_rub_num(ceiling_after_d)} ₽). Уменьшите финансирование или план "
                    f"по другим категориям субсидии{_lines_suffix}."
                ),
                "subsidy_id": subsidy_id_for_error,
                "total_plan": float(total_plan_after_d),
                "ceiling": float(ceiling_after_d),
                "over_amount": float(over_d),
                "over_before": float(over_before_d),
                "over_after": float(over_after_d),
                "over_root_categories": over_root_lines,
            },
        )

    await feo_history.record_updated(
        db, feo_history.ENTITY_FEO_CATEGORY, cat.id, user,
        {"budget": old_budget}, {"budget": float(new_budget)},
        source=source, source_ref=source_ref, commit=False,
    )

    return {
        "old_budget": old_budget,
        "new_budget": float(cat.budget),
        "subsidy_over_before": float(over_before_d),
        "subsidy_over_after": float(over_after_d),
    }


async def align_budget_to_plan_all(
    db: AsyncSession, user, subsidy_id: int,
    *, source: str = feo_history.SOURCE_MANUAL, source_ref: Optional[int] = None,
) -> dict:
    """Тело POST /api/subsidies/{subsidy_id}/feo/align-budget-to-plan-all —
    «Приравнять ФЭО к плану по всем статьям одним действием» (решение
    владельца 07.10.2026, план .planning/quick/2026-10-07-dnr-feo-cards/
    PLAN.md шаг 3, решение владельца №4): budget := node["plan"] + node["over"]
    (ТА ЖЕ формула цели, что и align_budget_to_plan выше — не вторая формула)
    у КАЖДОЙ категории субсидии сразу.

    БЕЗ потолочной проверки align_budget_to_plan по очереди на каждой
    категории: та проверка сравнивает «превышение субсидии ДО/ПОСЛЕ ОДНОЙ
    категории», пока остальные статьи ещё не выровнены — вызывать её по
    кругу на промежуточных состояниях бессмысленно (остальные статьи либо
    уже без ФЭО — не участвуют в потолке вовсе, см.
    app.services.subsidy_budget.feo_entered_ceiling_and_plan, — либо сами
    будут выровнены следующей итерацией этого же цикла). После ЭТОГО
    массового действия budget == plan У ВСЕХ категорий сразу — глобальное
    превышение равно нулю по построению, второй проверки не требуется.

    Возвращает {"count": сколько статей изменено, "total": сумма ФЭО по
    ВСЕЙ субсидии после действия (Σ по всем категориям, не только
    изменённым — именно это число показывает подтверждение на фронте: «ФЭО
    станет равным плану у N статей на сумму X ₽»)}."""
    from app.services.feo_plan import compute_feo_plan_tree

    cat_rows = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    if not cat_rows:
        return {"count": 0, "total": 0.0}

    tree = await compute_feo_plan_tree(db, [subsidy_id])
    count = 0
    total = Decimal("0")
    for cat in cat_rows:
        node = tree.get(cat.id)
        if node is None:
            continue
        new_budget = Decimal(str(node["plan"] + node["over"])).quantize(Decimal("0.01"))
        total += new_budget
        old_budget = float(cat.budget) if cat.budget is not None else None
        if old_budget is not None and abs(old_budget - float(new_budget)) < 0.005:
            continue  # уже равно плану — не плодить запись истории без изменения
        cat.budget = new_budget
        await feo_history.record_updated(
            db, feo_history.ENTITY_FEO_CATEGORY, cat.id, user,
            {"budget": old_budget}, {"budget": float(new_budget)},
            source=source, source_ref=source_ref, commit=False,
        )
        count += 1

    await db.flush()
    return {"count": count, "total": float(total)}
