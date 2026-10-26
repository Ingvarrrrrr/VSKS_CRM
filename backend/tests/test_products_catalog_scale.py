"""Сужение каталога под рост products к 250+ тыс. строк (владелец,
2026-10-26). Покрывает:
  - fetch_match_candidates (app/services/product_match_candidates.py) находит
    тот же товар, что и полный скан каталога, на маленькой фикстуре;
  - sql_dedup_normalized_name_expr (app/services/product_dedup_sql.py) даёт
    ТЕ ЖЕ группы дублей, что app.product_matcher._normalize;
  - 422 на превышение лимитов тела запроса (/match queries, /avg-price/bulk
    product_ids), ДО обращения к БД (ПРАВИЛО №8 п.6).

Полная сверка top-1/top-10 на 20 реальных названиях из боевых данных и
сверка числа групп дублей на всём локальном каталоге (26 336 товаров,
0 расхождений с Python _normalize) — отдельно, см. отчёт сессии и
backend/scripts/_qa_match_before_after.py / _qa_dedup_compare.py (не входят
в pytest — работают с живой БД контейнера, не с тестовой транзакцией)."""
import uuid

import pytest
from sqlalchemy import func, select

from app.models.product import Product
from app.product_matcher import _normalize
from app.routers.products_match import _MatchRequest, MAX_MATCH_QUERIES
from app.routers.plan_to_wish import _CandidatesRequest
from app.services.product_dedup_sql import sql_dedup_normalized_name_expr
from app.services.product_match_candidates import fetch_match_candidates

_UNIQ = "ТестСужениеКаталога_20261026"


def _uniq(suffix: str) -> str:
    return f"{_UNIQ} {suffix} {uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_fetch_match_candidates_finds_exact_product(db_session):
    name = _uniq("Бензорез Champion 3.5 кВт")
    p1 = Product(name=name, category="Прочее")
    p2 = Product(name=_uniq("Совсем другой товар"), category="Прочее")
    db_session.add_all([p1, p2])
    await db_session.commit()

    rows = await fetch_match_candidates(db_session, [name], org_id=None, active_only=False)
    ids = {r.id for r in rows}
    assert p1.id in ids, "trigram/ILIKE-кандидаты должны найти товар по точному имени query"


@pytest.mark.asyncio
async def test_fetch_match_candidates_word_fallback_for_short_query(db_session):
    """Короткое слово может оказаться ниже trigram similarity_threshold — AND-ILIKE
    по словам (та же _word_condition, что product_search.py) должен всё равно
    найти буквальное совпадение подстроки."""
    name = _uniq("ОУ-2")
    p = Product(name=name, category="Прочее")
    db_session.add(p)
    await db_session.commit()

    rows = await fetch_match_candidates(db_session, [name], org_id=None, active_only=False)
    ids = {r.id for r in rows}
    assert p.id in ids


@pytest.mark.asyncio
async def test_sql_dedup_matches_python_normalize_on_fixture(db_session):
    """Группа дублей (разный регистр/пробелы) — SQL-ключ должен дать ТОТ ЖЕ
    результат, что и app.product_matcher._normalize."""
    base = _uniq("Гофрокороб д600 Т24")
    dup1 = Product(name=base, category="Прочее")
    dup2 = Product(name=f"  {base.upper()}  ", category="Прочее")  # регистр + пробелы по краям
    other = Product(name=_uniq("Гофрокороб д500 Т22"), category="Прочее")  # другой товар — НЕ дубль
    db_session.add_all([dup1, dup2, other])
    await db_session.commit()

    norm_expr = sql_dedup_normalized_name_expr()
    rows = (await db_session.execute(
        select(Product.id, norm_expr.label("norm")).where(Product.id.in_([dup1.id, dup2.id, other.id]))
    )).all()
    norm_by_id = {r.id: r.norm for r in rows}

    assert norm_by_id[dup1.id] == norm_by_id[dup2.id] == _normalize(base)
    assert norm_by_id[other.id] != norm_by_id[dup1.id]

    dup_keys = (await db_session.execute(
        select(norm_expr)
        .where(Product.id.in_([dup1.id, dup2.id, other.id]))
        .group_by(norm_expr)
        .having(func.count() > 1)
    )).all()
    assert len(dup_keys) == 1
    assert dup_keys[0][0] == _normalize(base)


def test_match_request_rejects_too_many_queries():
    with pytest.raises(Exception):
        _MatchRequest(queries=["x"] * (MAX_MATCH_QUERIES + 1))
    # Граница — ровно MAX_MATCH_QUERIES ещё допустима.
    _MatchRequest(queries=["x"] * MAX_MATCH_QUERIES)


def test_plan_to_wish_candidates_request_rejects_too_many_ids():
    with pytest.raises(Exception):
        _CandidatesRequest(planned_item_ids=list(range(501)))
    _CandidatesRequest(planned_item_ids=list(range(500)))


@pytest.mark.asyncio
async def test_avg_price_bulk_rejects_too_many_product_ids(client, auth_headers):
    resp = await client.post(
        "/api/products/avg-price/bulk",
        json={"product_ids": list(range(1, 502))},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_avg_price_bulk_accepts_limit(client, auth_headers):
    resp = await client.post(
        "/api/products/avg-price/bulk",
        json={"product_ids": list(range(1, 11))},
        headers=auth_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_match_endpoint_rejects_too_many_queries(client, auth_headers):
    resp = await client.post(
        "/api/products/match",
        json={"queries": ["x"] * (MAX_MATCH_QUERIES + 1)},
        headers=auth_headers,
    )
    assert resp.status_code == 422
