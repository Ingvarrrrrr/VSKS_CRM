# -*- coding: utf-8 -*-
"""Правило №6 (волна C1/C2, 2026-09-07): «бюджет субсидии из дерева ФЭО» —
один источник истины (app.services.subsidy_budget), а не три копии одной
рекурсии (subsidies._budget_from_tree / feo_plan_reads.calc_budget) плюс
отдельная копия формулы фолбэка на ручной budget (dashboard.py).

Инвентаризация (см. отчёт волны): app.services.feo_plan.compute_feo_plan_tree
считает СОВСЕМ ДРУГУЮ величину (план/факт/заказ дерева с заменой плана
заказом) — её узловое поле "budget" читает FeoCategory.budget НАПРЯМУЮ, без
рекурсии «сумма детей». Формулы НЕ эквивалентны по построению (разное
назначение), поэтому она НЕ переведена на compute_budget_map — см. docstring
subsidy_budget.py. Тесты ниже покрывают именно ту рекурсию, что была
продублирована: агрегат бюджета субсидии и фолбэк на ручной budget.

Офлайн, синхронно (без реальной БД) — по образцу test_subsidy_draft.py.
"""
import asyncio
from types import SimpleNamespace

from app.services.subsidy_budget import (
    compute_budget_map,
    subsidy_budget_from_categories,
    effective_subsidy_budget,
)


def _cat(id, parent_id, level, budget=None):
    return SimpleNamespace(id=id, parent_id=parent_id, level=level, budget=budget)


# ---------------------------------------------------------------------------
# Три дерева из задания: плоское, override у родителя, NULL у листа.
# ---------------------------------------------------------------------------

def test_tree_flat_two_roots_sum():
    """Плоское дерево: два корня без детей, budget каждого — их собственный."""
    cats = [
        _cat(1, None, 1, budget=100_000),
        _cat(2, None, 1, budget=250_000),
    ]
    assert subsidy_budget_from_categories(cats) == 350_000
    budget_map = compute_budget_map(cats)
    assert budget_map == {1: 100_000.0, 2: 250_000.0}


def test_tree_parent_override_ignores_children_sum():
    """Родитель с явно заданным budget «отменяет авторасчёт по детям»
    (комментарий в модели FeoCategory.budget) — сумма детей ИГНОРИРУЕТСЯ,
    даже если она отличается от заданного вручную числа родителя."""
    cats = [
        _cat(1, None, 1, budget=500_000),   # root — ручной override
        _cat(2, 1, 2, budget=100_000),      # ребёнок 1
        _cat(3, 1, 2, budget=100_000),      # ребёнок 2 — сумма детей = 200 000 ≠ 500 000
    ]
    assert subsidy_budget_from_categories(cats) == 500_000
    budget_map = compute_budget_map(cats)
    assert budget_map[1] == 500_000.0  # override, не 200 000
    assert budget_map[2] == 100_000.0
    assert budget_map[3] == 100_000.0


def test_tree_null_leaf_and_null_parent_sums_children():
    """Лист без budget → 0.0 (не None, не ошибка). Родитель без budget →
    сумма детей (в т.ч. нулевых листьев)."""
    cats = [
        _cat(1, None, 1, budget=None),      # root, budget не задан → сумма детей
        _cat(2, 1, 2, budget=300_000),      # ребёнок с budget
        _cat(3, 1, 2, budget=None),         # ребёнок-лист без budget → 0.0
    ]
    assert subsidy_budget_from_categories(cats) == 300_000
    budget_map = compute_budget_map(cats)
    assert budget_map[3] == 0.0
    assert budget_map[1] == 300_000.0


def test_empty_tree_is_zero():
    assert subsidy_budget_from_categories([]) == 0.0
    assert compute_budget_map([]) == {}


# ---------------------------------------------------------------------------
# Фолбэк «дерево пустое → ручной subsidy.budget» — раньше пять независимых
# копий (list/detail/create/approve/update в subsidies.py + dashboard.py);
# create/approve/update НЕ применяли фолбэк вовсе (см. отчёт волны).
# ---------------------------------------------------------------------------

def test_effective_budget_uses_calc_when_tree_filled():
    assert effective_subsidy_budget(750_000, 1_000_000) == 750_000


def test_effective_budget_falls_back_to_manual_when_tree_empty():
    assert effective_subsidy_budget(0.0, 1_000_000) == 1_000_000


def test_effective_budget_falls_back_when_manual_budget_none():
    assert effective_subsidy_budget(0.0, None) == 0.0


def test_effective_budget_negative_calc_treated_as_empty():
    # Оборонительно: отрицательный calc не должен «победить» ручной budget.
    assert effective_subsidy_budget(-5.0, 1_000_000) == 1_000_000


# ---------------------------------------------------------------------------
# Dashboard и subsidies обязаны давать ОДНО число для одной субсидии — по
# построению (обе точки зовут effective_subsidy_budget), но фиксируем это
# явным тестом на конкретном сценарии (частично заполненное дерево + budget).
# ---------------------------------------------------------------------------

def test_dashboard_and_subsidies_share_one_formula_instance():
    from app.routers import dashboard as dashboard_module
    from app.routers import subsidies as subsidies_module

    assert dashboard_module.effective_subsidy_budget is subsidies_module.effective_subsidy_budget

    cats = [
        _cat(1, None, 1, budget=None),
        _cat(2, 1, 2, budget=420_000),
    ]
    calc = subsidy_budget_from_categories(cats)
    manual_budget = 1_000_000.0

    from_dashboard = dashboard_module.effective_subsidy_budget(calc, manual_budget)
    from_subsidies = subsidies_module.effective_subsidy_budget(calc, manual_budget)
    assert from_dashboard == from_subsidies == 420_000.0


# ---------------------------------------------------------------------------
# GET /api/subsidies/{id} и GET /api/subsidies/ БОЛЬШЕ НЕ пишут calculated_budget
# в БД (Правило №6 — колонка deprecated, считается на чтении).
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, obj=None):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj

    def first(self):
        return self._obj

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._obj, list):
            return self._obj
        return [self._obj] if self._obj is not None else []


class _CommitCountingFakeDB:
    """Как _FakeDB в test_subsidy_draft.py, но считает вызовы commit()."""

    def __init__(self, results=None):
        self._queue = list(results or [])
        self.commit_calls = 0

    async def execute(self, stmt):
        return self._queue.pop(0) if self._queue else _FakeResult(None)

    async def commit(self):
        self.commit_calls += 1

    async def refresh(self, obj):
        pass

    async def get(self, model, id):
        return None


def _mk_subsidy_obj(**kw):
    from app.models.subsidy import Subsidy as SubsidyModel
    defaults = dict(
        id=1, org_id=10, status="approved", created_by=5,
        contractor_id=None, name="ДНР_2026", year=2026, budget=1_000_000.0,
    )
    defaults.update(kw)
    s = SubsidyModel()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


def test_get_subsidy_detail_does_not_commit(monkeypatch):
    from app.routers import subsidies

    async def _fake_calc_budget(db, subsidy_id):
        return 0.0  # дерево пустое → ожидаем фолбэк на manual budget в ответе

    async def _fake_spent(db, subsidy_id):
        return 0.0

    async def _fake_planned(db, subsidy_id):
        return 0.0

    async def _fake_ceiling(db, subsidy_id):
        return {}

    monkeypatch.setattr(subsidies, "calculate_budget_from_categories", _fake_calc_budget)
    monkeypatch.setattr(subsidies, "_calculate_spent", _fake_spent)
    monkeypatch.setattr(subsidies, "_calculate_planned_amount", _fake_planned)
    monkeypatch.setattr(subsidies, "calculate_ceiling_forecast", _fake_ceiling)

    sub = _mk_subsidy_obj()
    db = _CommitCountingFakeDB(results=[_FakeResult(sub)])

    out = asyncio.run(subsidies.get_subsidy(1, db))

    assert db.commit_calls == 0, "GET не обязан писать calculated_budget в БД (Правило №6)"
    assert out["calculated_budget"] == 1_000_000.0  # фолбэк на ручной budget сработал
    assert out["feo_budget_total"] == 1_000_000.0
