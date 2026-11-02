"""Разбор страницы товара regard.ru — перенесено из
tools/harvest/stores/regard.py (ПРАВИЛО №6, единственный источник этой
логики). find_jsonld/manufacturer_article_from экспортируются отдельно,
т.к. используются ТАКЖЕ раздельской/фолбэк-веткой build_item в
tools/harvest/stores/regard.py (код в скобках на конце названия, когда
товар не посещался — StoreSpec.supports_details=False).

JSON-LD "Product" (brand, mpn) + пары
`CharacteristicsItem_name__<хеш>`/`CharacteristicsItem_value__<хеш>`;
"Код производителя" — артикул ПРОИЗВОДИТЕЛЯ (основной источник
manufacturer_article при визите)."""
from __future__ import annotations

import json
import re
from typing import Optional

_JSONLD_RE = re.compile(r'<script\s+type="application/ld\+json">([\s\S]*?)</script>')
_SPEC_ITEM_RE = re.compile(
    r'CharacteristicsItem_name__[\w]+"><span>([^<]*)</span>.*?'
    r'CharacteristicsItem_value__[\w]+">(.*?)</div></div>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_TRAILING_CODE_RE = re.compile(r"\(([^()]{4,})\)\s*$")
_JUNK_NAME_PREFIXES = ("технические характеристики",)
_JUNK_VALUE_PREFIXES = ("скачать",)


def find_jsonld(html: str, type_name: str) -> Optional[dict]:
    for block in _JSONLD_RE.findall(html):
        try:
            obj = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("@type") == type_name:
            return obj
    return None


def _parse_characteristics(html: str) -> list[dict]:
    characteristics = []
    for name, value_html in _SPEC_ITEM_RE.findall(html):
        name = name.strip()
        value = _TAG_RE.sub("", value_html).replace("&nbsp", " ").strip()
        if not name or not value:
            continue
        if name.strip().lower().startswith(_JUNK_NAME_PREFIXES):
            continue
        if value.strip().lower().startswith(_JUNK_VALUE_PREFIXES):
            continue
        characteristics.append({"name": name, "value": value, "unit": None, "in_description": False})
    return characteristics


def manufacturer_article_from(name: str, product_jsonld: dict, characteristics: list[dict]) -> Optional[str]:
    for c in characteristics:
        if c["name"].strip().lower() == "код производителя":
            return c["value"] or None

    mpn = product_jsonld.get("mpn")
    if mpn:
        return str(mpn).strip() or None

    # FALLBACK (без визита на товар): код в скобках на конце названия.
    m = _TRAILING_CODE_RE.search(name or "")
    if m and any(ch.isdigit() for ch in m.group(1)):
        return m.group(1).strip()
    return None


def parse_product_page(html: str, url: str) -> dict:
    product = find_jsonld(html, "Product") or {}
    characteristics = _parse_characteristics(html)
    name = product.get("name") or ""
    return {
        "jsonld_brand": product.get("brand"),
        "manufacturer_article": manufacturer_article_from(name, product, characteristics),
        "store_sku": str(product.get("sku")).strip() if product.get("sku") else None,
        "characteristics": characteristics,
    }
