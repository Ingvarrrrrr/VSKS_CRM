"""Разбор страницы товара magazin01.ru — перенесено из
tools/harvest/stores/magazin01.py (ПРАВИЛО №6, единственный источник этой
логики). ⚠️ фикстуры-источник СИНТЕТИЧЕСКИЕ (см. докстринг исходного
tools/harvest/stores/magazin01.py) — properties__title/properties__value
не подтверждены живой страницей, доработка значится там же.

JSON-LD "Product" (brand.name, sku — 13-значный ВНУТРЕННИЙ код магазина →
store_article, не manufacturer_article) + пары
`properties__title`/`properties__value`."""
from __future__ import annotations

import json
import re

BASE_URL = "https://magazin01.ru"

_LDJSON_RE = re.compile(r'application/ld\+json"[^>]*>([\s\S]*?)</script>')
_PROP_RE = re.compile(
    r'properties__title[^"]*"[^>]*>([^<]+)</div>\s*<span[^>]*>:</span>\s*'
    r'<div class="properties__value[^"]*"[^>]*>([^<]*)</div>'
)


def _find_jsonld_product(html: str) -> dict:
    for block in _LDJSON_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return {}


def parse_product_page(html: str, url: str) -> dict:
    product = _find_jsonld_product(html)
    name = product.get("name")
    if not name:
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
        name = re.sub(r"<[^>]+>", " ", h1.group(1)).strip() if h1 else None

    image = product.get("image")
    if isinstance(image, str):
        if image.startswith("//"):
            image = "https:" + image
        elif image.startswith("/"):
            image = BASE_URL + image

    offers = product.get("offers") or {}
    price = None
    if isinstance(offers, dict):
        price = offers.get("price")
    elif isinstance(offers, list) and offers:
        price = offers[0].get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    characteristics = []
    for raw_name, raw_value in _PROP_RE.findall(html):
        raw_name = re.sub(r"\?.*", "", raw_name).strip()
        raw_value = raw_value.strip()
        if raw_name and raw_value:
            characteristics.append({"name": raw_name, "value": raw_value, "unit": None, "in_description": False})

    brand = (product.get("brand") or {}).get("name") if isinstance(product.get("brand"), dict) else product.get("brand")

    return {
        "name": name,
        "description": product.get("description"),
        "photos": [image] if image else [],
        "price": price,
        "store_article": str(product.get("sku")).strip() if product.get("sku") else None,
        "jsonld_brand": brand,
        "characteristics": characteristics,
    }
