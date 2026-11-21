from __future__ import annotations

import logging
import re
import time
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.product_name_signature import (
    _brand_compare_key,
    _brand_phonetic_key,
    _is_recognizable_brand_word,
    _MANUAL_BRAND_PHONETIC_ALIASES,
    _phonetic_key_variants,
    _SHORT_BRAND_MAX_KEY_LEN,
    _SHORT_BRAND_WHITELIST_KEYS,
    _SIZE_TOKENS,
    fold_brand_or_code,
    is_bogus_manufacturer,
)

logger = logging.getLogger(__name__)

BRAND_CACHE_TTL_SECONDS = 30 * 60

_LATIN_RE = re.compile(r"[A-Za-z]")
_WORD_BOUNDARY_CHARS = r"a-zа-яё0-9"


class ManufacturerBrandDictionary:
    """`.find_in_name` того же контракта, что и BrandDictionary из
    tools/catalog_enrich — но построен из DISTINCT Product.manufacturer
    своей БД (is_bogus_manufacturer — тот же гейт качества, что в
    build_signature, Правило №6 — второй фильтр мусорных значений не
    заводим)."""

    def __init__(self, manufacturers: list) -> None:
        entries: dict = {}
        for name in manufacturers:
            if not name or is_bogus_manufacturer(name, ""):
                continue
            cmp_key = _brand_compare_key(name)
            if len(cmp_key) <= _SHORT_BRAND_MAX_KEY_LEN and cmp_key not in _SHORT_BRAND_WHITELIST_KEYS:
                continue
            key = fold_brand_or_code(name)
            if key and (key not in entries or (entries[key].islower() and not name.islower())):
                entries[key] = name
        self._entries = entries

        keys = sorted(entries.keys(), key=lambda k: (-len(k), k))
        if keys:
            pattern = (
                rf"(?<![{_WORD_BOUNDARY_CHARS}])"
                + rf"({'|'.join(re.escape(k) for k in keys)})"
                + rf"(?![{_WORD_BOUNDARY_CHARS}])"
            )
            self._regex = re.compile(pattern)
        else:
            self._regex = None

        phonetic_index: dict[str, list[tuple[str, str]]] = {}
        for folded_key, canonical in entries.items():
            base_pkey = _brand_phonetic_key(folded_key)
            if not base_pkey:
                continue
            for pkey in _phonetic_key_variants(base_pkey):
                phonetic_index.setdefault(pkey, []).append((folded_key, canonical))
            alias_pkeys = _MANUAL_BRAND_PHONETIC_ALIASES.get(folded_key) or ()
            for pkey in alias_pkeys:
                phonetic_index.setdefault(pkey, []).append((folded_key, canonical))
        self._phonetic_index = phonetic_index

    def find_in_name(self, name: Optional[str]) -> Optional[str]:
        if not name or not self._entries:
            return None
        text = fold_brand_or_code(name)
        if not text:
            return None

        exact = self._find_exact(text)
        if exact is not None:
            return exact

        return self._find_phonetic(name)

    def _find_exact(self, folded_text: str) -> Optional[str]:
        if not self._regex:
            return None
        m = self._regex.search(folded_text)
        if not m:
            return None
        matched_key = m.group(1)
        return self._entries.get(matched_key)

    def _find_phonetic(self, raw_name: str) -> Optional[str]:
        if not self._phonetic_index:
            return None

        cleaned = re.sub(r"[^\w\s-]", " ", raw_name)
        tokens = cleaned.split()
        for tok in tokens:
            raw_stripped = tok.strip("-")
            if not raw_stripped or not _is_recognizable_brand_word(raw_stripped):
                continue
            folded_tok = fold_brand_or_code(raw_stripped)
            if folded_tok in _SIZE_TOKENS:
                continue
            base_pkey = _brand_phonetic_key(folded_tok)
            if not base_pkey or len(base_pkey) < 3:
                continue

            candidates = self._phonetic_index.get(base_pkey)
            if candidates:
                return candidates[0][1]

        return None

    def __len__(self) -> int:
        return len(self._entries)


_brand_cache: dict = {
    "dictionary": None,
    "built_at": 0.0,
}


async def get_manufacturer_brand_dictionary(db: AsyncSession) -> ManufacturerBrandDictionary:
    """Возвращает кэшированный ManufacturerBrandDictionary.

    Кэш в памяти процесса на BRAND_CACHE_TTL_SECONDS (30 мин) — список
    distinct manufacturer меняется редко (только при импорте каталога),
    запрос DISTINCT по 247k товаров дорог для каждого поискового запроса.
    """
    now = time.monotonic()
    cached = _brand_cache.get("dictionary")
    built_at = _brand_cache.get("built_at", 0.0)

    if cached is not None and (now - built_at) < BRAND_CACHE_TTL_SECONDS:
        return cached

    result = await db.execute(
        select(Product.manufacturer)
        .where(Product.manufacturer.isnot(None), func.length(Product.manufacturer) > 0)
        .distinct()
    )
    manufacturers = [row[0] for row in result.all() if row[0]]

    dictionary = ManufacturerBrandDictionary(manufacturers)
    _brand_cache["dictionary"] = dictionary
    _brand_cache["built_at"] = now
    logger.info("Построен ManufacturerBrandDictionary: %d уникальных брендов", len(dictionary))
    return dictionary
