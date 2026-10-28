# -*- coding: utf-8 -*-
"""Тесты для app.auth.account_contour_cache (перф-правка 28.10.2026, прод-
жалоба «GET /api/purchases/?scope=purchases&with_feo_excess=true 12.5с,
следующий такой же запрос — 500 за 15.1с»).

Профиль на стенде (backend/profile_warm2.py, см. сессию) показал:
apply_purchase_visibility зовёт app.auth.visibility.compute_account_contour_org_ids
18 раз за ОДИН HTTP-запрос (14× с одним и тем же org_id, 4× с другим) —
get_visible_subsidy_ids/get_visible_user_ids/exclude_hidden_payroll_purchases
независимо резолвят иерархию, не зная, что контур ЭТОГО org_id уже посчитан
соседом. Это тест на ДВА инварианта кэша (ПРАВИЛО №6 — кэш, не вторая формула):

1) Результат ОДИНАКОВ с открытым account_contour_request_scope() и без него
   (кэш не меняет данные, только избавляет от повторного счёта).
2) В ПРЕДЕЛАХ одного открытого scope() повторный вызов с ТЕМ ЖЕ org_id не
   доходит до настоящей (uncached) реализации.

ДОПОЛНЕНО (владелец, 28.10.2026, тот же замер — compute_account_contour_org_ids
пересчитывался заново КАЖДЫЙ HTTP-запрос): под request-scope кэшем добавлен
ВТОРОЙ, межзапросный слой (account_contour_cache.get_or_compute_cross_request,
LRU версионированный по organizations — см. docstring модуля). Поэтому
инвариант №2 из исходного докстринга («без scope каждый вызов пересчитывает
заново») больше НЕ ВЕРЕН буквально — без scope несколько вызовов с тем же
org_id ТЕПЕРЬ ТОЖЕ не доходят до настоящей реализации повторно, если версия
organizations не менялась (это и есть цель задачи). Тест ниже проверяет обе
границы межзапросного слоя явно, очищая его between арраnжировками
(clear_global_cache) там, где нужно изолировать именно request-scope слой."""
import uuid

import pytest

from app.auth.account_contour_cache import account_contour_request_scope, clear_global_cache
from app.auth.visibility import compute_account_contour_org_ids
import app.auth.visibility as visibility_module


@pytest.fixture(autouse=True)
def _reset_global_lru():
    clear_global_cache()
    yield
    clear_global_cache()


async def _make_org(db_session, owner_user_id=None, root_org_id=None):
    from app.models.contractor import Contractor
    from app.models.organization import Organization
    name = f"ContourCacheOrg-{uuid.uuid4().hex[:8]}"
    contractor = Contractor(name=name)
    db_session.add(contractor)
    await db_session.flush()
    org = Organization(contractor_id=contractor.id, owner_user_id=owner_user_id, root_org_id=root_org_id)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.mark.asyncio
async def test_cached_result_matches_uncached_result(db_session):
    """Инвариант №1: с кэшем и без него — одно и то же множество org_id."""
    root = await _make_org(db_session)
    child = await _make_org(db_session, root_org_id=root.id)

    without_scope = await compute_account_contour_org_ids(db_session, root.id)

    with account_contour_request_scope():
        with_scope = await compute_account_contour_org_ids(db_session, root.id)

    assert without_scope == with_scope
    assert root.id in without_scope
    assert child.id in without_scope


@pytest.mark.asyncio
async def test_scope_deduplicates_repeated_calls_same_org_id(db_session, monkeypatch):
    """Инвариант №2 (request-scope): внутри ОДНОГО открытого scope повторные
    вызовы с тем же org_id не доходят до настоящей реализации."""
    root = await _make_org(db_session)
    calls = {"n": 0}
    orig = visibility_module._compute_account_contour_org_ids_direct

    async def _counting(db, org_id):
        calls["n"] += 1
        return await orig(db, org_id)

    monkeypatch.setattr(visibility_module, "_compute_account_contour_org_ids_direct", _counting)

    # Без ЛЮБОГО кэша (межзапросный LRU очищен ПЕРЕД каждым вызовом) — 3
    # вызова с одним org_id считают 3 раза: это изолирует именно отсутствие
    # request-scope кэша, не задевая межзапросный слой (он проверяется
    # отдельно ниже и в test_cross_request_cache_survives_without_scope).
    calls["n"] = 0
    for _ in range(3):
        clear_global_cache()
        await compute_account_contour_org_ids(db_session, root.id)
    assert calls["n"] == 3

    # С открытым scope — 3 вызова с одним org_id считают 1 раз (request-scope
    # кэш отдаёт результат без обращения даже к межзапросному слою).
    clear_global_cache()
    calls["n"] = 0
    with account_contour_request_scope():
        for _ in range(3):
            await compute_account_contour_org_ids(db_session, root.id)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_cross_request_cache_survives_without_scope(db_session, monkeypatch):
    """Новое поведение (28.10.2026): БЕЗ открытого request-scope (имитация
    двух РАЗНЫХ HTTP-запросов — jwt.get_current_user и т.п. не открывают
    account_contour_request_scope()) повторный вызов с тем же org_id ВСЁ
    РАВНО не доходит до настоящей реализации — за это отвечает межзапросный
    LRU (версия organizations не менялась)."""
    root = await _make_org(db_session)
    calls = {"n": 0}
    orig = visibility_module._compute_account_contour_org_ids_direct

    async def _counting(db, org_id):
        calls["n"] += 1
        return await orig(db, org_id)

    monkeypatch.setattr(visibility_module, "_compute_account_contour_org_ids_direct", _counting)

    for _ in range(3):
        await compute_account_contour_org_ids(db_session, root.id)
    assert calls["n"] == 1

    # Изменение organizations бампает версию → следующий вызов пересчитывает.
    from app.models.organization import Organization
    child = Organization(root_org_id=root.id)
    db_session.add(child)
    await db_session.commit()

    await compute_account_contour_org_ids(db_session, root.id)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_scope_keys_cache_by_org_id_separately(db_session, monkeypatch):
    """Разные org_id — разные записи кэша, не схлопываются в одну (иначе
    закупки/видимость разных организаций перемешались бы в одном запросе)."""
    org_a = await _make_org(db_session)
    org_b = await _make_org(db_session)
    calls = {"n": 0}
    orig = visibility_module._compute_account_contour_org_ids_direct

    async def _counting(db, org_id):
        calls["n"] += 1
        return await orig(db, org_id)

    monkeypatch.setattr(visibility_module, "_compute_account_contour_org_ids_direct", _counting)

    with account_contour_request_scope():
        res_a1 = await compute_account_contour_org_ids(db_session, org_a.id)
        res_b1 = await compute_account_contour_org_ids(db_session, org_b.id)
        res_a2 = await compute_account_contour_org_ids(db_session, org_a.id)

    assert calls["n"] == 2  # org_a считан раз, org_b считан раз, повтор org_a — из кэша
    assert res_a1 == res_a2
    assert org_a.id in res_a1 and org_a.id not in res_b1
