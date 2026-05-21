"""Token-based fuzzy product matching service (Phase 27.4-25).

Algorithm:
1. normalize(s) — lower + strip punctuation (re.sub(r'[^\w\s\d]', ' ')) + collapse spaces
2. tokenize(s) — split by whitespace, keep tokens with len>=2, drop NOISE_TOKENS
3. stem(t) — t[:6] if len(t)>6 (primitive Russian-suffix stemming)
4. score(query, catalog_name) — weighted coverage + SequenceMatcher ratio
5. bulk_match(queries, catalog, top_k, threshold) — batch score, return MatchResult list
"""
import re
import logging
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from typing import Optional

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuneable thresholds
# ---------------------------------------------------------------------------

SCORE_AUTO = 0.95     # auto-accept: no human review needed
SCORE_SUGGEST = 0.60  # suggest: show candidates to user for review

# ---------------------------------------------------------------------------
# Noise tokens stripped before scoring
# ---------------------------------------------------------------------------

NOISE_TOKENS = {
    'кг', 'шт', 'мл', 'л', 'см', 'мм', 'м', 'упак', 'пач', 'кор',
    'пара', 'и', 'в', 'на', 'для', 'с', 'из', 'от', 'по', 'за',
    'или', 'а', 'но', 'к', 'до', 'над', 'под',
}

_RE_PUNCT = re.compile(r'[^\w\s\d]')
_RE_WS = re.compile(r'\s+')


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def normalize(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if not s:
        return ''
    s = s.lower()
    s = _RE_PUNCT.sub(' ', s)
    s = _RE_WS.sub(' ', s).strip()
    return s


def tokenize(s: str) -> list[str]:
    """Split normalized string into meaningful tokens (len>=2, not noise)."""
    return [t for t in normalize(s).split() if len(t) >= 2 and t not in NOISE_TOKENS]


def stem(t: str) -> str:
    """Primitive 6-char prefix stem for Russian suffix handling."""
    return t[:6] if len(t) > 6 else t


def score(query: str, catalog_name: str) -> float:
    """Compute similarity score between query and one catalog entry name.

    Returns float in [0.0, 1.0].
    """
    q_tokens = {stem(t) for t in tokenize(query)}
    c_tokens = {stem(t) for t in tokenize(catalog_name)}

    if not q_tokens:
        return 0.0

    intersection = q_tokens & c_tokens
    coverage = len(intersection) / len(q_tokens)

    seq = SequenceMatcher(None, normalize(query), normalize(catalog_name)).ratio()

    combined = 0.7 * coverage + 0.3 * seq

    # Boost: full query coverage with at least 2 meaningful tokens
    if coverage == 1.0 and len(q_tokens) >= 2:
        combined = max(combined, 0.95)

    return combined


# ---------------------------------------------------------------------------
# Batch matching
# ---------------------------------------------------------------------------

@dataclass
class CandidateResult:
    product_id: int
    name: str
    price: Optional[float]
    score: float


@dataclass
class MatchResult:
    query: str
    status: str  # 'auto' | 'suggest' | 'create'
    candidates: list[CandidateResult] = field(default_factory=list)


def bulk_match(
    queries: list[str],
    catalog: list[tuple[int, str, Optional[float]]],
    top_k: int = 3,
    threshold: float = SCORE_SUGGEST,
) -> list[MatchResult]:
    """Score each query against the full catalog; return top_k candidates per query.

    Args:
        queries: list of name strings from the import/UI
        catalog: list of (product_id, name, price) tuples loaded from DB
        top_k: max candidates to return per query
        threshold: minimum score to include a candidate (default SCORE_SUGGEST)

    Returns:
        list of MatchResult, one per query, preserving input order.
        status='auto'    if best score >= SCORE_AUTO
        status='suggest' if SCORE_SUGGEST <= best score < SCORE_AUTO
        status='create'  if best score < SCORE_SUGGEST (or catalog empty)
    """
    results: list[MatchResult] = []

    for query in queries:
        if not query or not query.strip():
            results.append(MatchResult(query=query, status='create', candidates=[]))
            continue

        scored: list[CandidateResult] = []
        for pid, name, price in catalog:
            s = score(query, name or '')
            if s >= threshold:
                scored.append(CandidateResult(
                    product_id=pid,
                    name=name or '',
                    price=float(price) if price is not None else None,
                    score=round(s, 4),
                ))

        # Sort descending by score, take top_k
        scored.sort(key=lambda x: x.score, reverse=True)
        candidates = scored[:top_k]

        if not candidates:
            status = 'create'
        elif candidates[0].score >= SCORE_AUTO:
            status = 'auto'
        else:
            status = 'suggest'

        results.append(MatchResult(query=query, status=status, candidates=candidates))

    return results
