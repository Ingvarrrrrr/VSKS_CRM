"""Fuzzy product matching by name (Phase 21.x post-deploy fix).

Use case: receipt parsers / purchase upload feed item names like
"Карабин Ozone с байонетной муфтой" while catalog has "Ozone с байонетной
муфтой" (with type stored separately as "Карабин"). Exact match misses,
result is a duplicate Product row in the catalog.

Strategy: token-set overlap (Jaccard-like) over normalized lowercase tokens
with stopwords stripped. Threshold 0.7 — tuned to catch the carabiner case
without false positives across truly different products.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


_STOP = {
    'и', 'в', 'с', 'на', 'для', 'из', 'по', 'к', 'от', 'до', 'за', 'над',
    'под', 'или', 'либо', 'но', 'а', 'же', 'ли', 'бы', 'вр', 'тд', 'тп',
}
_PUNCT = re.compile(r'[\"\'«»()\[\],.;:!?@#%&*=+/\\—–\-_…]')
_WS = re.compile(r'\s+')


def _normalize(s: str) -> str:
    if not s:
        return ''
    s = unicodedata.normalize('NFKC', s).lower()
    s = s.replace('ё', 'е')  # ё→е (равнозначные в каталоге)
    s = _PUNCT.sub(' ', s)
    s = _WS.sub(' ', s).strip()
    return s


def _tokens(name: str) -> set:
    if not name:
        return set()
    parts = _normalize(name).split(' ')
    return {p for p in parts if p and len(p) > 1 and p not in _STOP}


def name_similarity(a: str, b: str) -> float:
    """Combined similarity in [0, 1]: max(token-set overlap, char ratio).

    Token-set catches reordering and inserted prefixes ("Карабин Ozone..." vs
    "Ozone..."). SequenceMatcher catches typos / minor character variation
    that token-set misses ("Тренажер" vs "Тренажёр" → after ё→е normalization
    these are identical, but other typos remain).
    """
    if not a or not b:
        return 0.0
    ta, tb = _tokens(a), _tokens(b)
    token_score = 0.0
    if ta and tb:
        inter = ta & tb
        if inter:
            token_score = len(inter) / max(len(ta), len(tb))
    char_score = SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()
    return max(token_score, char_score)


async def find_matching_product(
    db: AsyncSession,
    name: str,
    *,
    org_id: Optional[int] = None,
    threshold: float = 0.7,
) -> Optional[Product]:
    """Find the best-matching Product for a given name.

    Tries exact case-insensitive match first (cheap), then falls back to
    token-set fuzzy match. Returns the highest-scoring product above
    `threshold`, or None.

    org_id, if given, restricts the search to that organization's catalog.
    """
    name = (name or '').strip()
    if not name:
        return None

    # Exact case-insensitive (single round-trip)
    q = select(Product).where(func.lower(Product.name) == name.lower())
    if org_id is not None:
        q = q.where(Product.org_id == org_id)
    exact = (await db.execute(q.limit(1))).scalar_one_or_none()
    if exact:
        return exact

    # Fuzzy: load candidates, score in Python.
    # For 10k-product catalogs this is still <50ms; if it grows we can
    # pre-filter by trigram or ts_vector.
    q = select(Product)
    if org_id is not None:
        q = q.where(Product.org_id == org_id)
    candidates: Iterable[Product] = (await db.execute(q)).scalars().all()

    best: Optional[Product] = None
    best_score = 0.0
    for c in candidates:
        score = name_similarity(name, c.name or '')
        if score > best_score:
            best_score = score
            best = c
    if best is not None and best_score >= threshold:
        return best
    return None
