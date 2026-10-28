"""account_contour_cache.py — request-scoped мемо-кэш compute_account_contour_org_ids
(тот же приём, что app.services.feo_plan_tree_cache — ПРАВИЛО №6: формула
compute_account_contour_org_ids не трогается ни на символ, это прозрачный кэш
ВОКРУГ неё).

Повод (прод-жалоба 27.10.2026: GET /api/purchases/?scope=purchases&with_feo_excess=true
12.5с, следующий такой же запрос — 500 за 15.1с; профиль на стенде, user_id=5
account_owner, 308 закупок/11 субсидий): app.services.purchase_list_visibility.
apply_purchase_visibility зовёт get_visible_subsidy_ids/build_visibility_clause/
get_visible_user_ids/exclude_hidden_payroll_purchases — каждая по отдельности
резолвит иерархию видимости и НЕ знает, что остальные уже посчитали контур ТЕХ
ЖЕ org_id. Замер (count_calls3.py): compute_account_contour_org_ids вызвана 18
раз за ОДИН HTTP-запрос — 14 раз с org_id=1, 4 раза с org_id=29, каждый раз
пересчитывая ОДИН И ТОТ ЖЕ результат (BFS по Organization, до 5 раундов, 2-3
SQL на раунд) заново: ~20мс × 18 = ~360мс из ~780мс apply_purchase_visibility.

Область жизни — ОДИН HTTP-запрос (contextvars.ContextVar), НЕ глобальный
процесс: состав организаций меняется между запросами (создание/перепривязка
орг), кэш между запросами запрещён (тот же принцип, что у feo_plan_tree_cache —
см. её докстринг). Ключ — org_id (int), т.к. compute_account_contour_org_ids —
чистая функция от (org_id, БД-состояние на момент запроса).

ПРОД-ЗАМЕР (владелец, 28.10.2026, тот же замер, что feo_plan_tree_cache):
apply_purchase_visibility — 0,34с/578 SQL, большая часть от compute_account_
contour_org_ids, пересчитываемого заново КАЖДЫЙ HTTP-запрос. Добавлен второй,
межзапросный слой (_global_cache) ПОД request-scope выше: ключ — (org_id,
глобальная версия "оргструктура", account_contour_versions.py — бампается
ЕДИНСТВЕННЫМ триггером на organizations, см. миграцию f5a7c9e1b3d5 — это
единственная таблица, которую реально читает _compute_account_contour_org_ids_
uncached, см. её докстринг). Любое изменение organizations (создание/перепривязка
root_org_id/owner_user_id) бампает версию → следующий запрос промахивается и
пересчитывает. LRU на 256 org_id (контур — set[int], лёгкий, org_id в проекте
не десятки тысяч)."""
import copy
import functools
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

_cache_var: ContextVar[Optional[dict]] = ContextVar("account_contour_cache", default=None)

_GLOBAL_LRU_MAX = 256
_global_cache: "OrderedDict[tuple, set]" = OrderedDict()


@contextmanager
def account_contour_request_scope():
    """Открывает memo-область на время одного запроса. Вложенный вызов
    безопасен — см. docstring feo_plan_tree_cache.feo_plan_tree_request_scope,
    тот же механизм token/reset."""
    token = _cache_var.set({})
    try:
        yield
    finally:
        _cache_var.reset(token)


def get_cached_contour(org_id) -> Optional[set]:
    cache = _cache_var.get()
    if cache is None:
        return None
    return cache.get(org_id)


def store_cached_contour(org_id, contour: set) -> None:
    cache = _cache_var.get()
    if cache is None:
        return
    cache[org_id] = contour


async def get_or_compute_cross_request(db, org_id, compute_fn) -> set[int]:
    """Межзапросный слой (см. докстринг модуля) — ключ (org_id, версия
    organizations). compute_fn — исходная НЕкэширующая
    _compute_account_contour_org_ids_uncached (ПРАВИЛО №6, формула не
    трогается). Возвращает КОПИЮ множества — чужой код мутирующий результат
    `|=`/`.add()` не испортит запись в LRU для остальных подписчиков."""
    from app.services.subsidy_calc_versions import get_account_contour_version

    if not org_id:
        return await compute_fn(db, org_id)

    version = await get_account_contour_version(db)
    key = (int(org_id), version)

    cached = _global_cache.get(key)
    if cached is not None:
        _global_cache.move_to_end(key)
        return set(cached)

    contour = await compute_fn(db, org_id)
    _global_cache[key] = set(contour)
    _global_cache.move_to_end(key)
    while len(_global_cache) > _GLOBAL_LRU_MAX:
        _global_cache.popitem(last=False)
    return contour


def clear_global_cache() -> None:
    """Для тестов — полный сброс межзапросного LRU между независимыми кейсами."""
    _global_cache.clear()


def with_account_contour_cache(fn):
    """Декоратор для роутов — открывает account_contour_request_scope() вокруг
    ВСЕГО вызова (тот же приём, что with_feo_plan_tree_cache)."""

    @functools.wraps(fn)
    async def _wrapped(*args, **kwargs):
        with account_contour_request_scope():
            return await fn(*args, **kwargs)

    return _wrapped
