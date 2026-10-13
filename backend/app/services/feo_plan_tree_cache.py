"""feo_plan_tree_cache.py — request-scoped мемо-кэш compute_feo_plan_tree (Правило №5/№6).

Повод (владелец, 2026-10-12): прод GET /api/dashboard/charts — 7-15 с, uvicorn
(1 worker) почти не отвечает другим запросам все это время. Профиль на стенде
(user_id=5, 23 видимые субсидии): compute_feo_plan_tree (feo_plan_tree.py)
строился дважды за запрос (3,4 с → 1,9 с после кэша) — несколько мест запроса
(_calculate_feo_planned_tree_bulk в routers/subsidies.py,
subsidy_money_summary.py и их внутренние Σ-функции — committed_amounts.py,
type_totals.py, feo_plan_totals.py) принимают СВОЙ опциональный `tree=`, но
каждое МЕСТО, где его явно не передали, строит дерево заново — тот же набор
subsidy_ids пересчитывается по многу раз за один HTTP-запрос.

ПРАВИЛО №6: это НЕ второй механизм расчёта дерева — сама формула
(compute_feo_plan_tree) не трогается ни на символ. Это прозрачный кэш ВОКРУГ
неё (см. обёртку в конце feo_plan_tree.py), общий для ВСЕХ ~30 вызывающих мест
по всему проекту — им не нужно знать о существовании кэша и передавать что-то
новое, они продолжают звать compute_feo_plan_tree(db, subsidy_ids) как раньше.

Область жизни — ОДИН HTTP-запрос (contextvars.ContextVar), а не глобальный
процесс: данные (закупки/план) меняются между запросами, кэш между ними
запрещён явно задачей владельца. Scope открывает вызывающий код (сейчас —
dashboard_charts.py) через `with feo_plan_tree_request_scope():` вокруг тела
обработчика; без открытого scope (обычные одиночные вызовы — GET одной
субсидии, запись дерева и т.п.) кэш просто не участвует, поведение прежнее.

Ключ кэша — frozenset(subsidy_ids): разные места дашборда неизменно зовут
дерево с ОДНИМ И ТЕМ ЖЕ полным списком видимых subsidy_ids за один запрос
(sid_list), совпадение набора гарантирует совпадение результата (чистая
функция от БД-состояния, которое не меняется в рамках одного запроса).
"""
import functools
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

_cache_var: ContextVar[Optional[dict]] = ContextVar("feo_plan_tree_cache", default=None)


@contextmanager
def feo_plan_tree_request_scope():
    """Открывает memo-область на время одного запроса. Вложенный вызов (scope
    внутри уже открытого scope, например из сабфункции) безопасен — снаружи
    кэш переживает выход из внутреннего `with`, потому что token восстанавливает
    ИМЕННО то значение ContextVar, что было до входа в этот конкретный `with`."""
    token = _cache_var.set({})
    try:
        yield
    finally:
        _cache_var.reset(token)


def get_cached_tree(subsidy_ids) -> Optional[dict]:
    cache = _cache_var.get()
    if cache is None:
        return None
    return cache.get(frozenset(subsidy_ids))


def store_cached_tree(subsidy_ids, tree: dict) -> None:
    cache = _cache_var.get()
    if cache is None:
        return
    cache[frozenset(subsidy_ids)] = tree


def with_feo_plan_tree_cache(fn):
    """Декоратор для роутов — открывает feo_plan_tree_request_scope() вокруг
    ВСЕГО вызова, без необходимости переотступать (reindent) тело функции.
    Применён на GET /api/dashboard/charts (dashboard_charts.py) — минимальный
    дифф в большом существующем файле (Правило №5/№6, см. докстринг модуля)."""

    @functools.wraps(fn)
    async def _wrapped(*args, **kwargs):
        with feo_plan_tree_request_scope():
            return await fn(*args, **kwargs)

    return _wrapped
