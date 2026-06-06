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
SCORE_DIFFERENT = 0.40  # ниже этого — почти наверняка другой товар, не предлагаем вовсе

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
    """27.4-27: Прогрессивное сужение по словам (как просил пользователь).

    Алгоритм:
      1. Разбить query на токены [t1, t2, t3, ...]
      2. pool = весь каталог
      3. Для каждого t_i подряд:
         - next = [товары из pool где stem(t_i) есть в множестве токенов товара]
         - если next пусто:
              если это первое слово И pool ещё не суженный → товар отсутствует → 'create'
              иначе → остановиться, вернуть текущий pool как 'suggest'
         - pool = next
         - если len(pool) == 1: stop (нашли уникальный)

    Возвращает (status, candidates):
      - 'create' если первое же слово не сужает (= товара нет ни у кого)
      - 'auto' если pool == 1 И ВСЕ токены query покрыты этим единственным товаром
      - 'suggest' иначе (1 элемент но не полное покрытие; либо несколько)
    """
    q_tokens = tokenize(query)
    if not q_tokens:
        return 'create', []

    q_stems = [stem(t) for t in q_tokens]

    pool = catalog_indexed
    matched_stem_count = 0
    for q_stem in q_stems:
        next_pool = [entry for entry in pool if q_stem in entry[3]]
        if not next_pool:
            # Этот токен ни у кого из pool нет
            if matched_stem_count == 0:
                # Даже первый токен query не нашёлся → товар отсутствует
                return 'create', []
            # Часть токенов матчила; остановиться на предыдущем pool
            break
        pool = next_pool
        matched_stem_count += 1
        if len(pool) == 1:
            break

    # Превращаем оставшийся pool в CandidateResult
    candidates: list[CandidateResult] = []
    for entry in pool:
        pid, name, price, c_stems = entry[0], entry[1], entry[2], entry[3]
        description = entry[4] if len(entry) > 4 else None
        photo_url = entry[5] if len(entry) > 5 else None
        item_type = entry[6] if len(entry) > 6 else None
        category = entry[7] if len(entry) > 7 else None
        # Score = доля токенов query покрытых в catalog tokens
        coverage = len([s for s in q_stems if s in c_stems]) / len(q_stems)
        candidates.append(CandidateResult(
            product_id=pid,
            name=name,
            price=float(price) if price is not None else None,
            score=round(coverage, 4),
            description=description,
            photo_url=photo_url,
            item_type=item_type,
            category=category,
        ))

    candidates.sort(key=lambda x: x.score, reverse=True)

    # Отсекаем заведомо чужие товары: при <40% покрытия это почти наверняка
    # совсем другой товар — не зашумляем выбор пользователя ложными кандидатами.
    candidates = [c for c in candidates if c.score >= SCORE_DIFFERENT]
    if not candidates:
        return 'create', []

    if len(candidates) == 1 and candidates[0].score >= 1.0:
        return 'auto', candidates
    return 'suggest', candidates


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
