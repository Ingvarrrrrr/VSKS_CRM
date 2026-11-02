"""Разбор страницы товара kuvalda.ru (JSON-LD "Product" + таблица
характеристик) — перенесено из tools/harvest/stores/kuvalda.py (ПРАВИЛО
№6, единственный источник этой логики). tools/harvest/stores/kuvalda.py
загружает parse_product_page/_find_jsonld отсюда через _backend_bridge
(обратный normal-импорт backend.app.* потянул бы весь пакет приложения,
см. докстринг моста); живой поиск (store_search/take.py) использует эту же
функцию при довизите на страницу товара ПОСЛЕ «Взять».

Чисто stdlib (re/json) — никаких зависимостей от остального backend, чтобы
модуль одинаково грузился и внутри приложения, и в изолированном
tools/harvest.

JSON-LD "Product": brand {"@type":"Brand","name":"MAKITA"}, sku="DP4010" —
явный артикул производителя; характеристики —
class="product-specs__characteristics-item"><span>Имя</span><span>
Значение</span>. Подробности и источник вёрстки — см. историю
tools/harvest/stores/kuvalda.py (git log)."""
from __future__ import annotations

import json
import re
from typing import Optional

_SPEC_ITEM_RE = re.compile(
    r'product-specs__characteristics-item">\s*<span>([^<]*)</span>\s*<span>([^<]*)</span>'
)
_JSONLD_RE = re.compile(r'<script\s+type="application/ld\+json"[^>]*>([\s\S]*?)</script>')


def find_jsonld(html: str, type_name: str) -> Optional[dict]:
    """Ищет первый JSON-LD блок с заданным @type (используется и для
    разбора страницы раздела — OfferCatalog, и страницы товара —
    Product)."""
    for block in _JSONLD_RE.findall(html):
        try:
            obj = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("@type") == type_name:
            return obj
    return None


def parse_product_page(html: str, url: str) -> dict:
    product = find_jsonld(html, "Product") or {}
    characteristics = [
        {"name": name.strip(), "value": value.strip() or None, "unit": None, "in_description": False}
        for name, value in _SPEC_ITEM_RE.findall(html)
        if name.strip()
    ]
    return {
        "jsonld_brand": product.get("brand"),
        "manufacturer_article": (str(product.get("sku")).strip() if product.get("sku") else None),
        "characteristics": characteristics,
        "description": product.get("description"),
    }
