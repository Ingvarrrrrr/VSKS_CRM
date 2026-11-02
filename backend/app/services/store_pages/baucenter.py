"""Разбор страницы товара baucenter.ru (Next.js data-роут JSON) —
перенесено из tools/harvest/stores/baucenter.py (ПРАВИЛО №6, единственный
источник этой логики). pageProps.initialState.product.currentProductData.
product.properties[] (code,title,value) — настоящие характеристики; страна
— свойство с title, начинающимся на "Страна"."""
from __future__ import annotations

import html as _html
import json
import re
from typing import Optional

_COUNTRY_TITLE_RE = re.compile(r"^страна", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_description(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    text = _TAG_RE.sub(" ", raw)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def parse_product_page(html_text: str, url: str) -> dict:
    try:
        data = json.loads(html_text)
    except (json.JSONDecodeError, ValueError):
        return {}
    product = (
        data.get("pageProps", {})
        .get("initialState", {})
        .get("product", {})
        .get("currentProductData", {})
        .get("product", {})
    )
    characteristics = []
    country = None
    for prop in product.get("properties") or []:
        title = (prop.get("title") or "").strip()
        value = (prop.get("value") or "").strip()
        if not title or not value:
            continue
        characteristics.append({"name": title, "value": value, "unit": None, "in_description": False})
        if _COUNTRY_TITLE_RE.match(title):
            country = value
    return {
        "brand": (product.get("brand") or "").strip() or None,
        "characteristics": characteristics,
        "description": _clean_description(product.get("description")),
        "country_origin": country,
    }
