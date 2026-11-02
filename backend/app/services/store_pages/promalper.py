"""Разбор страницы товара promalper.com — перенесено из
tools/harvest/stores/promalper.py (ПРАВИЛО №6, единственный источник этой
логики). WooCommerce product_attributes таблица
`<th>Имя</th><td>Значение</td>` — единственный источник бренда ("Бренд") и
страны ("Страна бренда"); manufacturer_article всегда None (отдельного
поля на странице нет)."""
from __future__ import annotations

import json
import re

_LDJSON_RE = re.compile(r'<script\s+type="application/ld\+json"[^>]*>([\s\S]*?)</script>')
_ATTR_ROW_RE = re.compile(r"<th[^>]*>([^<]+)</th>\s*<td[^>]*>([\s\S]*?)</td>")
_TAG_RE = re.compile(r"<[^>]+>")


def _find_jsonld_product(html: str) -> dict:
    for block in _LDJSON_RE.findall(html):
        try:
            obj = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        graph = obj.get("@graph", [obj]) if isinstance(obj, dict) else obj
        for node in graph if isinstance(graph, list) else [graph]:
            if isinstance(node, dict) and node.get("@type") == "Product":
                return node
    return {}


def parse_product_page(html: str, url: str) -> dict:
    product = _find_jsonld_product(html)
    name = product.get("name")

    offers = product.get("offers")
    price = None
    if isinstance(offers, list) and offers:
        price = offers[0].get("price")
    elif isinstance(offers, dict):
        price = offers.get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    characteristics = []
    brand = None
    country = None
    for raw_name, raw_value in _ATTR_ROW_RE.findall(html):
        name_clean = raw_name.strip()
        value_clean = _TAG_RE.sub(" ", raw_value).strip()
        if not name_clean or not value_clean:
            continue
        characteristics.append({"name": name_clean, "value": value_clean, "unit": None, "in_description": False})
        name_lower = name_clean.lower()
        if name_lower == "бренд":
            brand = value_clean
        elif name_lower == "страна бренда":
            country = value_clean

    image = product.get("image")

    return {
        "name": name,
        "price": price,
        "store_article": str(product.get("sku")).strip() if product.get("sku") else None,
        "jsonld_brand": brand,
        "characteristics": characteristics,
        "country_origin": country,
        "photos": [image] if isinstance(image, str) and image.startswith("http") else [],
    }
