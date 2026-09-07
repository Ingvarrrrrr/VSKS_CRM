# -*- coding: utf-8 -*-
"""Единый источник истины (Правило №6) для «бюджета субсидии из дерева ФЭО».

Формула узла: budget = собственный FeoCategory.budget, если задан вручную,
иначе сумма budget прямых детей (рекурсивно). Бюджет субсидии = сумма этой
величины по корневым узлам (level == 1).

До этой правки формула была продублирована ТРИ раза:
  1) app.routers.subsidies._budget_from_tree — агрегат по субсидии (роуты
     list/detail/create/approve/update).
  2) app.routers.feo_plan_reads.calc_budget (эндпоинт /budget-residuals) —
     та же рекурсия, но по требованию для конкретного узла (направления и
     листья с ancestors), не только сумма корней.
  3) app.routers.dashboard — копия формулы фолбэка «расчёт из дерева, а
     если дерево пустое (0) — ручное subsidy.budget» (effective_budget).

Теперь обе части (рекурсия по дереву + фолбэк на ручной budget) живут
здесь. app.routers.subsidies.calculate_budget_from_categories/
calculate_budgets_bulk остаются тонкими обёртками — их продолжают
импортировать app.routers.dashboard, app.routers.feo_tree_ops,
app.routers.purchase_budget, app.services.feo_plan, и монкипатчить тесты
(test_subsidy_draft.py: `monkeypatch.setattr(subsidies,
"calculate_budget_from_categories", ...)`).

⚠️ НЕ путать с app.services.feo_plan.compute_feo_plan_tree — та функция
считает СОВСЕМ ДРУГУЮ величину: «план/факт/заказ» дерева (plan_manual,
ordered, over, display — с заменой плана заказом при наборе количества),
а не агрегат «финансирование по дереву ФЭО». Её узловое поле "budget" —
это СОБСТВЕННОЕ (не рекурсивное) значение FeoCategory.budget, читаемое
напрямую из строки категории и используемое только для сравнения
план vs финансирование на каждом узле (excess-проверки). Рекурсии
«сумма детей, если NULL» там нет — дублирования с этим файлом нет.
Если это когда-либо изменится (compute_feo_plan_tree начнёт считать
агрегат по дереву сама), её нужно перевести на compute_budget_map()
отсюда, а не заводить четвёртую копию.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory


def compute_budget_map(categories: Iterable) -> dict:
    """budget по КАЖДОМУ узлу переданного набора категорий одного дерева
    (не только по корням): собственный FeoCategory.budget, если задан,
    иначе сумма budget прямых детей (рекурсивно, с мемоизацией).

    Общая для:
      - subsidy_budget_from_categories (сумма по корневым узлам, агрегат
        бюджета субсидии);
      - app.routers.feo_plan_reads /budget-residuals (точечный budget
        любого узла — направления/листа/предка).
    """
    cats = list(categories)
    by_id = {c.id: c for c in cats}
    children_map: dict = {}
    for c in cats:
        children_map.setdefault(c.id, [])
        if c.parent_id is not None and c.parent_id in by_id:
            children_map.setdefault(c.parent_id, []).append(c)

    memo: dict = {}

    def _calc(cat) -> float:
        if cat.id in memo:
            return memo[cat.id]
        kids = children_map.get(cat.id, [])
        if not kids:
            val = float(cat.budget) if cat.budget is not None else 0.0
        elif cat.budget is not None:
            val = float(cat.budget)
        else:
            val = sum(_calc(k) for k in kids)
        memo[cat.id] = val
        return val

    for c in cats:
        _calc(c)
    return memo


def subsidy_budget_from_categories(categories: Iterable) -> float:
    """Агрегат «бюджет субсидии из дерева ФЭО» — сумма budget (см.
    compute_budget_map) по корневым узлам (level == 1). Единственная
    реализация рекурсии для этой величины в проекте."""
    cats = list(categories)
    if not cats:
        return 0.0
    budget_map = compute_budget_map(cats)
    roots = [c for c in cats if c.level == 1]
    return sum(budget_map.get(r.id, 0.0) for r in roots)


def effective_subsidy_budget(calc: float, manual_budget: Optional[float]) -> float:
    """Формула фолбэка: расчёт из дерева ФЭО, а если дерево пустое
    (calc <= 0, категорий ещё нет/не заполнены) — ручное значение
    subsidy.budget. Решение 14.07: budget — ручное значение, деревом
    ФЭО НЕ перезаписывается — но при пустом дереве оно единственный
    источник для "бюджет субсидии"."""
    calc = float(calc or 0.0)
    return calc if calc > 0 else float(manual_budget or 0)


async def calculate_budget_from_categories(db: AsyncSession, subsidy_id: int) -> float:
    result = await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )
    return subsidy_budget_from_categories(result.scalars().all())


async def calculate_budgets_bulk(db: AsyncSession, subsidy_ids: list) -> dict:
    """Бюджеты для набора субсидий одним запросом (вместо N запросов в списках)."""
    if not subsidy_ids:
        return {}
    result = await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id.in_(subsidy_ids))
    )
    by_subsidy: dict = {}
    for c in result.scalars().all():
        by_subsidy.setdefault(c.subsidy_id, []).append(c)
    return {
        sid: subsidy_budget_from_categories(by_subsidy.get(sid, []))
        for sid in subsidy_ids
    }
