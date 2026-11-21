from __future__ import annotations

import time
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, bindparam, text as sa_text
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.product_name_signature import (
    _PRODUCT_TYPE_WINDOW,
    _split_words,
)
from app.services.product_name_signature_props import (
    PRODUCT_TYPE_PHRASES,
    PRODUCT_TYPE_WORDS,
)

if TYPE_CHECKING:
    from app.services.product_query_parse import ParsedQuery


def product_type_synonyms(product_type: Optional[str]) -> list[str]:
    """Все слова (PRODUCT_TYPE_WORDS) и фразы (PRODUCT_TYPE_PHRASES) из
    словаря, которые канонизируются в данный `product_type` — для
    product_search.py: tsquery по виду товара строится как OR этих
    написаний вместо ОДНОГО литерального слова из запроса."""
    if not product_type:
        return []
    out: set[str] = set()
    for word, canon in PRODUCT_TYPE_WORDS.items():
        if canon == product_type:
            out.add(word)
    for phrase, canon in PRODUCT_TYPE_PHRASES.items():
        if canon == product_type:
            out.add(phrase)
    return sorted(out)


_TYPE_STEM_CACHE_TTL_SECONDS = 30 * 60
_type_stem_cache: dict = {"index": None, "built_at": 0.0}


async def _get_type_stem_index(db: AsyncSession) -> dict:
    """stem(слово PRODUCT_TYPE_WORDS) → канонический вид — кэш в памяти
    процесса."""
    now = time.monotonic()
    cached = _type_stem_cache["index"]
    if cached is not None and (now - _type_stem_cache["built_at"]) < _TYPE_STEM_CACHE_TTL_SECONDS:
        return cached

    words = sorted(PRODUCT_TYPE_WORDS.keys())
    stmt = sa_text(
        "SELECT w, (ts_lexize('russian_stem', w))[1] AS stem FROM unnest(:words) AS w"
    ).bindparams(bindparam("words", type_=PG_ARRAY(String)))
    rows = (await db.execute(stmt, {"words": words})).all()
    index: dict = {}
    for word, stem in rows:
        if stem:
            index[stem] = PRODUCT_TYPE_WORDS[word]
    _type_stem_cache["index"] = index
    _type_stem_cache["built_at"] = now
    return index


async def resolve_type_by_stem(db: AsyncSession, parsed: "ParsedQuery") -> "ParsedQuery":
    """Если parse_query() НЕ распознала вид товара буквально
    (parsed.product_type is None) — пробуем по СТЕМУ."""
    from app.services.product_query_parse import ParsedQuery

    if parsed.product_type is not None:
        return parsed

    words = _split_words(parsed.raw, fold_homoglyphs=False)[:_PRODUCT_TYPE_WINDOW]
    candidates = [w for w in words if w in parsed.optional]
    if not candidates:
        return parsed

    index = await _get_type_stem_index(db)
    if not index:
        return parsed

    stmt = sa_text(
        "SELECT w, (ts_lexize('russian_stem', w))[1] AS stem FROM unnest(:words) AS w"
    ).bindparams(bindparam("words", type_=PG_ARRAY(String)))
    rows = (await db.execute(stmt, {"words": candidates})).all()
    stem_by_word = {word: stem for word, stem in rows}

    for w in candidates:
        canon = index.get(stem_by_word.get(w))
        if canon:
            new_required = [*parsed.required, w]
            new_optional = [o for o in parsed.optional if o != w]
            return ParsedQuery(
                raw=parsed.raw,
                required=new_required,
                optional=new_optional,
                dropped_stopwords=parsed.dropped_stopwords,
                specific=parsed.specific,
                brand=parsed.brand,
                product_type=canon,
                type_literal=w,
            )
    return parsed
