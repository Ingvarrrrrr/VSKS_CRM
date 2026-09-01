"""Этап A (шапка заявки не видит категорию ФЭО с планом, заданным вручную):
GET /feo-categories/flat вычисляет структурный признак has_plan трёмя независимыми
источниками — planned_quantity×planned_amount, активные FeoPlannedItem (фолбэк на
мигрированные категории-листья) и plan_source='manual_sum' с manual_plan_amount > 0
(план введён одной суммой). До правки третий источник отсутствовал: категория с
ручным планом (manual_sum) считалась has_plan=False и пропадала из дерева выбора
категории ФЭО в шапке заявки (useFeoLeaves.filterFundedNodes режет узлы без
has_budget/has_plan и без профинансированных потомков).

Синхронный тест на подставных объектах (SimpleNamespace) — без БД, без async —
покрывает чистую функцию app.routers.feo_categories._category_has_plan.
"""
from types import SimpleNamespace

from app.routers.feo_categories import _category_has_plan


def _cat(
    id=1,
    planned_quantity=None,
    planned_amount=None,
    plan_source="planned_items",
    manual_plan_amount=None,
):
    return SimpleNamespace(
        id=id,
        planned_quantity=planned_quantity,
        planned_amount=planned_amount,
        plan_source=plan_source,
        manual_plan_amount=manual_plan_amount,
    )


def test_has_plan_true_from_planned_quantity_and_amount():
    cat = _cat(planned_quantity=2, planned_amount=1000)
    assert _category_has_plan(cat, cats_with_plan_items=set()) is True


def test_has_plan_true_from_active_planned_items_fallback():
    # planned_quantity/planned_amount пусты (мигрированная категория-лист), но под ней
    # есть активная FeoPlannedItem с amount > 0 — id категории попал в предвычисленный
    # набор cats_with_plan_items.
    cat = _cat(id=42, planned_quantity=None, planned_amount=None)
    assert _category_has_plan(cat, cats_with_plan_items={42}) is True


def test_has_plan_true_from_manual_sum_plan_source():
    # Регресс этой задачи: план введён одной суммой (plan_source='manual_sum'),
    # planned_quantity/planned_amount не заполнены.
    cat = _cat(
        planned_quantity=None,
        planned_amount=None,
        plan_source="manual_sum",
        manual_plan_amount=500000,
    )
    assert _category_has_plan(cat, cats_with_plan_items=set()) is True


def test_has_plan_false_when_manual_sum_amount_is_zero():
    cat = _cat(
        plan_source="manual_sum",
        manual_plan_amount=0,
    )
    assert _category_has_plan(cat, cats_with_plan_items=set()) is False


def test_has_plan_false_when_manual_sum_amount_is_none():
    cat = _cat(plan_source="manual_sum", manual_plan_amount=None)
    assert _category_has_plan(cat, cats_with_plan_items=set()) is False


def test_has_plan_false_when_nothing_set():
    cat = _cat()
    assert _category_has_plan(cat, cats_with_plan_items=set()) is False


def test_has_plan_false_when_planned_items_present_for_other_category():
    cat = _cat(id=7)
    assert _category_has_plan(cat, cats_with_plan_items={99}) is False
