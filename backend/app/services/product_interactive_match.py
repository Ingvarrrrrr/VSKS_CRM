"""Интерактивный матчинг строки позиции — через КАТАЛОЖНЫЙ поиск, не через
app.product_matcher.bulk_match (владелец, 29.10.2026, ПРАВИЛО №6, задание
п.B): жалоба — строка позиции («огнетушитель оп-2») и страница «Товары» на
ОДНО И ТО ЖЕ действие «найти товар по тексту» давали РАЗНЫЙ порядок, потому
что ходили в ДВА разных механизма (POST /products/match →
app.services.product_matcher.bulk_match — нечёткие стемы; каталог →
app.services.product_search.search_products — FTS-лестница + ранжирование
по виду/бренду/числу). Это и есть нарушение Правила №6 — "один показатель,
один источник" применимо и к порядку результатов одного и того же поиска.

Используется ТОЛЬКО когда признак интерактивного набора установлен —
POST /api/products/match с prefix=True (app/routers/products_match.py,
_MatchRequest.prefix) — ЕДИНСТВЕННЫЙ вызывающий код. Пакетный импорт/
дедуп/автосопоставление (prefix=False, см. docstring там) ПРОДОЛЖАЕТ идти
через bulk_match — другая задача (сопоставить КАЖДУЮ строку накладной с
товаром каталога по нечёткому совпадению слов), её лестница ослабления
намеренно отличается от поиска по строке набора, второй механизм здесь не
заменяет первый, а добавляется РЯДОМ для другого режима работы того же
эндпоинта (см. docstring _MatchRequest.prefix).

candidate-форма — ТА ЖЕ, что строит products_match.py::_score_product_candidates
(dict с полями _MatchCandidate) — здесь строится НАПРЯМУЮ из Product ORM-строк,
которые уже отдаёт search_products (без второго SELECT по id, как у
bulk_match-пути — там это нужно, потому что catalog собирается отдельным
узким SQL-предвыбором, здесь полные объекты уже есть)."""
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.item_types import normalize_item_type
from app.services.price_freshness import FreshnessContext, evaluate as evaluate_freshness
from app.services.product_search import ProductSearchFilters, search_products
from app.services.product_snapshot import resolve_photo_url

# Статус 'auto' — ТОЛЬКО при действительно точном совпадении имени (без
# учёта регистра/краевых пробелов) — владелец, 29.10.2026, задание п.B:
# bulk_match раньше ставил 'auto' (score>=0.95) любому нечёткому совпадению
# стемов, из-за чего РАЗНЫЕ марки огнетушителя получали одинаковые ложные
# 100%. Здесь score осмысленный — убывает по позиции в каталожном порядке
# (search_products уже отранжировал кандидатов — тип/бренд/число/опечатки/
# ts_rank, см. докстринг там), не одна и та же цифра у всех.
_AUTO_SCORE = 100.0
_SUGGEST_SCORE_START = 92.0
_SUGGEST_SCORE_STEP = 6.0
_SUGGEST_SCORE_FLOOR = 35.0

# Потолок результатов каталога, которые реально нужно превратить в
# кандидатов (фронт — InlineProductMatch.vue — просит limit=100, но
# инвариант тот же, что у bulk_match-пути в products_match.py: top_k
# ограничен сверху, Правило №8 п.4 — вход валидируется до запроса, не
# бесконечный список в ответе).
MAX_INTERACTIVE_CANDIDATES = 200


def _candidate_score(rank: int, is_exact: bool) -> float:
    if is_exact:
        return _AUTO_SCORE
    return max(_SUGGEST_SCORE_FLOOR, _SUGGEST_SCORE_START - rank * _SUGGEST_SCORE_STEP)


def _candidate_from_product(p, rank: int, is_exact: bool, freshness_ctx: Optional[FreshnessContext]) -> dict:
    freshness = evaluate_freshness(p, freshness_ctx) if freshness_ctx is not None else None
    return {
        "product_id": p.id,
        "name": p.name,
        "price": float(p.price) if p.price is not None else None,
        "score": _candidate_score(rank, is_exact),
        "description": p.description,
        "photo_url": resolve_photo_url(p.photo_url, bool(p.photo_size), p.id),
        "item_type": normalize_item_type(p.item_kind) or p.item_kind,
        "category": p.category,
        "product_type": p.product_type,
        "unit": p.unit,
        "country_origin": p.country_origin,
        "price_updated_at": p.price_updated_at.isoformat() if p.price_updated_at else None,
        "price_source": p.price_source,
        "price_source_ref": p.price_source_ref,
        "price_freshness": freshness,
    }


async def interactive_match_one(
    db: AsyncSession,
    query: str,
    *,
    limit: int,
    freshness_ctx: Optional[FreshnessContext],
    active_only: bool = False,
) -> dict:
    """Один query → {"query", "status", "candidates": [...]} — ТОЙ ЖЕ формы,
    что и bulk_match-путь (products_match.py::_score_product_candidates), но
    кандидаты и их ПОРЯДОК — напрямую из search_products (та же функция,
    тот же порядок, что у GET /api/products/page, Правило №6)."""
    q = (query or "").strip()
    if not q:
        return {"query": query, "status": "create", "candidates": []}

    top_k = max(1, min(limit, MAX_INTERACTIVE_CANDIDATES))
    filters = ProductSearchFilters(search=q, is_active=True if active_only else None)
    items, _total, _capped = await search_products(db, filters, limit=top_k, offset=0)

    q_fold = q.lower()
    candidates: List[dict] = []
    for rank, p in enumerate(items):
        is_exact = (p.name or "").strip().lower() == q_fold
        candidates.append(_candidate_from_product(p, rank, is_exact, freshness_ctx))

    if not candidates:
        status = "create"
    elif candidates[0]["score"] >= _AUTO_SCORE:
        status = "auto"
    else:
        status = "suggest"
    return {"query": query, "status": status, "candidates": candidates}


async def interactive_match_candidates(
    db: AsyncSession,
    queries: List[str],
    *,
    limit: int,
    freshness_ctx: Optional[FreshnessContext],
    active_only: bool = False,
) -> List[dict]:
    """Список query (на практике — ОДИН, см. docstring модуля и
    InlineProductMatch.vue) → список результатов в том же порядке, что
    queries — последовательно, не батчем (каждый вызывает ПОЛНУЮ лестницу
    search_products, которая сама по себе лёгкая — см. докстринг
    product_search.py про 200мс-бюджет на 247 тыс. товаров; объединять
    несколько queries в один SQL-проход здесь не нужно — интерактивный
    набор шлёт ОДНУ строку на запрос)."""
    return [
        await interactive_match_one(db, q, limit=limit, freshness_ctx=freshness_ctx, active_only=active_only)
        for q in queries
    ]
