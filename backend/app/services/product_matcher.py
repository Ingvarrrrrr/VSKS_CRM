"""Token-based fuzzy product matching service (Phase 27.4-25).

Implementation moved to app.services.text_match (Step 4, план
zany-fluttering-mountain.md, шаг 4: «не заводить пятую копию нормализации») — this
module is now a thin product-specific wrapper: it re-exports the generic
normalize/tokenize/stem/score/thresholds unchanged (products.py и
purchase_items_import.py импортируют их отсюда — сигнатуры и поведение НЕ менялись,
трогать эти файлы не нужно), and builds the product-shaped CandidateResult/
MatchResult on top of the shared `generic_progressive_match` narrowing engine.
"""
from dataclasses import dataclass, field
from typing import Optional

from app.services.text_match import (
    normalize, tokenize, stem, score,
    NOISE_TOKENS, SCORE_AUTO, SCORE_SUGGEST, SCORE_DIFFERENT,
    generic_progressive_match,
)

__all__ = [
    "normalize", "tokenize", "stem", "score", "NOISE_TOKENS",
    "SCORE_AUTO", "SCORE_SUGGEST", "SCORE_DIFFERENT",
    "CandidateResult", "MatchResult", "progressive_match", "bulk_match",
]


# ---------------------------------------------------------------------------
# Batch matching (product-shaped candidates)
# ---------------------------------------------------------------------------

@dataclass
class CandidateResult:
    product_id: int
    name: str
    price: Optional[float]
    score: float
    description: Optional[str] = None
    photo_url: Optional[str] = None
    item_type: Optional[str] = None
    category: Optional[str] = None


@dataclass
class MatchResult:
    query: str
    status: str  # 'auto' | 'suggest' | 'create'
    candidates: list[CandidateResult] = field(default_factory=list)


def progressive_match(
    query: str,
    catalog_indexed: list[tuple[int, str, Optional[float], set[str], Optional[str], Optional[str], Optional[str], Optional[str]]],
) -> tuple[str, list[CandidateResult]]:
    """27.4-27: Прогрессивное сужение по словам — обёртка над
    text_match.generic_progressive_match, строит product-специфичные CandidateResult.

    `catalog_indexed` entries: (product_id, name, price, stem_set, description,
    photo_url, item_type, category) — как и раньше, см. bulk_match ниже.

    Возвращает (status, candidates) — семантика status не изменилась (см.
    text_match.generic_progressive_match docstring).
    """
    indexed = [(entry, entry[3]) for entry in catalog_indexed]
    status, scored = generic_progressive_match(query, indexed)

    candidates: list[CandidateResult] = []
    for entry, sc in scored:
        pid, name, price = entry[0], entry[1], entry[2]
        description = entry[4] if len(entry) > 4 else None
        photo_url = entry[5] if len(entry) > 5 else None
        item_type = entry[6] if len(entry) > 6 else None
        category = entry[7] if len(entry) > 7 else None
        candidates.append(CandidateResult(
            product_id=pid,
            name=name,
            price=float(price) if price is not None else None,
            score=sc,
            description=description,
            photo_url=photo_url,
            item_type=item_type,
            category=category,
        ))
    return status, candidates


def bulk_match(
    queries: list[str],
    catalog: list[tuple],
    top_k: int = 3,
    threshold: float = SCORE_SUGGEST,
) -> list[MatchResult]:
    """27.4-27: прогрессивное сужение по словам (вместо score-based fuzzy).

    Алгоритм по требованию пользователя:
      «Не брать всю фразу сразу. Вводит слова — из БД вылезают совпадения как
       интерактивный фильтр. Если по первому слову 0 — товара нет, добавлять.
       Если несколько — следующие слова, пока не останется один похожий.»

    status:
      - 'auto'    — найден единственный товар покрывающий все токены query
      - 'suggest' — несколько кандидатов (≥1) или 1 кандидат с неполным покрытием
      - 'create'  — даже первый токен ни в одном товаре каталога не встречается
    """
    # Pre-compute token set для каждого товара каталога (избегаем повторного tokenize)
    # catalog entries: (id, name, price[, description, photo_url, item_type, category])
    catalog_indexed = [
        (
            entry[0],
            entry[1] or '',
            entry[2],
            {stem(t) for t in tokenize(entry[1] or '')},
            entry[3] if len(entry) > 3 else None,  # description
            entry[4] if len(entry) > 4 else None,  # photo_url
            entry[5] if len(entry) > 5 else None,  # item_type
            entry[6] if len(entry) > 6 else None,  # category
        )
        for entry in catalog
    ]

    results: list[MatchResult] = []
    for query in queries:
        if not query or not query.strip():
            results.append(MatchResult(query=query, status='create', candidates=[]))
            continue
        status, candidates = progressive_match(query, catalog_indexed)
        # Ограничиваем top_k для UI
        results.append(MatchResult(
            query=query,
            status=status,
            candidates=candidates[:top_k],
        ))
    return results
