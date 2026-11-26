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

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.product_catalog_match import find_exact_product as _find_exact_product


_STOP = {
    'и', 'в', 'с', 'на', 'для', 'из', 'по', 'к', 'от', ' до', 'за', 'над',
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

    # Exact match (Правило №6, единая точка входа — app/services/product_catalog_match.py):
    # обрезка пробелов по краям + схлопывание внутренних + lower(); при
    # дублях с одинаковым именем предпочитает запись с заполненным описанием
    # («сопоставление предпочитает запись с ТЗ», владелец 2026-09-14).
    exact = await _find_exact_product(db, name, org_id=org_id, include_org_null=False)
    if exact:
        return exact

    # Шаг 2 (fuzzy): безопасная SQL-предфильтрация (OOM prevention on large catalogs)
    # - Выбирать в SQL ТОЛЬКО лёгкие колонки `select(Product.id, Product.name)`
    # - Фильтр Product.is_active == True и Product.org_id == org_id (если org_id is not None)
    # - Топ-3 самых длинных токена (длиной >= 3, или все токены если длинных нет)
    # - .limit(500)
    all_toks = list(_tokens(name))
    if not all_toks:
        return None
    # Сортировка по убыванию длины, берем топ-3
    sorted_toks = sorted(all_toks, key=len, reverse=True)
    top_tokens = sorted_toks[:3]
    if not top_tokens:
        return None

    q = select(Product.id, Product.name).where(Product.is_active == True)
    if org_id is not None:
        q = q.where(Product.org_id == org_id)

    # Экранирование % и _ для ilike (autoescape=True или явное через icontains)
    conditions = [Product.name.icontains(tok, autoescape=True) for tok in top_tokens]
    q = q.where(or_(*conditions)).limit(500)

    rows = (await db.execute(q)).all()

    best_id: Optional[int] = None
    best_score = 0.0
    for pid, pname in rows:
        score = name_similarity(name, pname or '')
        if score > best_score:
            best_score = score
            best_id = pid

    if best_id is not None and best_score >= threshold:
        return await db.get(Product, best_id)
    return None
