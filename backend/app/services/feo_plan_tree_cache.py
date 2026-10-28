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

ПРОД-ЗАМЕР (владелец, 28.10.2026): GET /api/purchases/?with_feo_excess=true —
3,35с одиночно, из них compute_feo_plan_tree 1,64с (11 субсидий) — та же
формула пересчитывается КАЖДЫЙ HTTP-запрос, даже когда между запросами никто
ничего не менял (план/закупки статичны минуты и часы). Request-scoped кэш
выше не помогает МЕЖДУ запросами — добавлен второй, межзапросный слой
(_GlobalTreeCache) ПОД ним же: сначала проверяется request-scope (без SQL
вообще), и только при его промахе — глобальный LRU, ключ которого включает
версии субсидий (subsidy_calc_versions.py, бампается триггерами Postgres —
см. миграцию f5a7c9e1b3d5) — изменение ЛЮБЫХ данных дерева инвалидирует
ключ автоматически, без ручного invalidate(). Хранение — LRU на 64 записи
(сервер почти без свободной RAM, см. задачу): ключ — не субсидия, а НАБОР
subsidy_ids (разные вызывающие места обычно зовут дерево с одним и тем же
полным списком видимых субсидий, поэтому 64 записи — это 64 РАЗНЫХ набора,
более чем достаточно на практике)."""
import copy
import functools
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

_cache_var: ContextVar[Optional[dict]] = ContextVar("feo_plan_tree_cache", default=None)

_GLOBAL_LRU_MAX = 64
_global_cache: "OrderedDict[tuple, dict]" = OrderedDict()


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


async def get_or_compute_cross_request(db, subsidy_ids, compute_fn) -> dict:
    """Межзапросный слой (см. докстринг модуля): ключ = (набор subsidy_ids,
    версия КАЖДОЙ из них + глобальная строка) — один лёгкий запрос
    (get_subsidy_versions, subsidy_calc_versions.py) на ВСЕ запрошенные
    субсидии разом. compute_fn — исходная НЕкэширующая compute_feo_plan_tree
    (ПРАВИЛО №6 — формула не трогается, это обёртка вокруг неё).

    Возвращает ГЛУБОКУЮ КОПИЮ закэшированного дерева — вызывающий код по
    всему проекту свободно читает узлы (`node["x"]`), но хранить в LRU
    общий для всех запросов объект и отдавать его БЕЗ копии небезопасно:
    один вызывающий код случайно мутирует узел — испортит кэш для всех
    остальных подписчиков этого же ключа навсегда (до следующего bump)."""
    from app.services.subsidy_calc_versions import get_subsidy_versions

    ids = sorted({int(x) for x in subsidy_ids})
    if not ids:
        return await compute_fn(db, subsidy_ids)

    versions = await get_subsidy_versions(db, ids)
    key = (tuple(ids), tuple(versions.get(i, 1) for i in ids), versions.get(0, 1))

    cached = _global_cache.get(key)
    if cached is not None:
        _global_cache.move_to_end(key)
        return copy.deepcopy(cached)

    tree = await compute_fn(db, subsidy_ids)
    _global_cache[key] = copy.deepcopy(tree)
    _global_cache.move_to_end(key)
    while len(_global_cache) > _GLOBAL_LRU_MAX:
        _global_cache.popitem(last=False)
    return tree


def _global_cache_len() -> int:
    """Для тестов — размер LRU без доступа к приватной переменной напрямую."""
    return len(_global_cache)


def clear_global_cache() -> None:
    """Для тестов — полный сброс межзапросного LRU между независимыми кейсами
    (иначе тест B может увидеть запись, оставленную тестом A на том же
    процессе pytest)."""
    _global_cache.clear()


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
