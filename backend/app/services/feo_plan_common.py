"""feo_plan_common.py — приватные хелперы, общие для 2+ модулей семейства feo_plan.

Вынесено из feo_plan.py (рефакторинг без изменения поведения, сессия
2026-09-08, см. ПРАВИЛО №5). `_leaf_plan_manual` нужен и feo_plan_excess.py
(find_excess_culprit), и feo_plan_tz_checks.py (assert_tz_not_over_plan) —
единственная точка формулы плана листа при plan_source='manual_sum', чтобы
она не разошлась при разъезде по разным файлам (ПРАВИЛО №6).
"""
from typing import Optional


def _leaf_plan_manual(
    plan_source: Optional[str], manual_plan_amount, items_total: float, excess_approved: bool,
) -> tuple:
    """Общая точка с compute_feo_plan_tree._manual_plan_for (тот же переключатель
    FeoCategory.plan_source, ОДИН узел) — задача 2, отчёт сессии 2026-09-03.

    _manual_plan_for — приватный closure ВНУТРИ compute_feo_plan_tree (завязан на
    батчевые словари всей субсидии: leaf_item_amt/own_manual_excess/
    latest_approval_by_cat), поэтому find_excess_culprit не может вызвать его
    напрямую — вместо этого воспроизводит ЕЁ ЖЕ формулу здесь, как отдельную
    независимо тестируемую точку (без доступа к closure-словарям, только на
    переданных аргументах). compute_feo_plan_tree._manual_plan_for сознательно
    НЕ трогалась при этом рефакторинге (следующая задача правит
    assert_no_unapproved_excess/эту область отдельно) — идентичность формул
    доказывается тестом test_find_excess_culprit_uses_same_plan_source_formula
    в test_feo_plan_tree_scenarios.py, сравнивающим числа обеих функций на одних
    данных, а не совместным вызовом кода.

    ДО задачи 2 find_excess_culprit вообще не знал о plan_source — использовал
    REMOVED-формулу «оба поля planned_quantity и planned_amount не пустые →
    qty×amt, иначе Σ FeoPlannedItem» (угадывание по пустым полям), удалённую из
    compute_feo_plan_tree коммитом f8d68bc (2026-08-13, «способ расчёта плана
    задаётся переключателем, а не угадывается по пустым полям»). Из-за этого
    расхождения find_excess_culprit мог назвать пользователю цифру плана, НЕ
    совпадающую с той, из-за которой реально сработала блокировка.

    Формула (см. FeoCategory.plan_source, docstring compute_feo_plan_tree):
      'planned_items' (умолчание) — план узла = items_total (Σ активных
        FeoPlannedItem, считает вызывающий код), excess_plan_over_manual = 0.
      'manual_sum' — план узла = manual_plan_amount, ПОКА накопленное
        превышение (items_total − manual_plan_amount) не согласовано; когда
        excess_approved=True (последний PlanExcessApproval ИМЕННО этого узла
        approved) — план узла становится items_total.

    Возвращает (manual_plan_entered, plan_manual, excess_plan_over_manual) — те
    же три величины, что и первые три элемента кортежа _manual_plan_for."""
    items_total = float(items_total)
    if (plan_source or "planned_items") != "manual_sum":
        return 0.0, items_total, 0.0
    manual_amt = float(manual_plan_amount) if manual_plan_amount is not None else 0.0
    excess = items_total - manual_amt
    if excess <= 0.005:
        excess = 0.0
    plan_manual = manual_amt
    if excess > 0.005 and excess_approved:
        plan_manual = items_total
    return manual_amt, plan_manual, excess
