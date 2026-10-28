"""Адаптер живого поиска magazin01.ru — этап 1 «живой поиск товара в
магазинах», владелец, 28.10.2026.

Проверено на живых фикстурах (backend/tests/fixtures/store_search/
magazin01.html — запрос «огнетушитель», magazin01_product.html — страница
товара): Bitrix-поиск (`/search/?q=<query>`) отдаёт только ссылку+название+
сниппет (искомое слово обёрнуто в `<b>`), БЕЗ цены и фото — страница вообще
не несёт карточки товара, только текстовый список (включая посторонние
результаты — статьи блога `/blog/...` — такие строки пропускаются, товар
только `/product/...`). Цена/фото/бренд — довизит на страницу товара,
JSON-LD `"@type":"Product"` → `offers.price`, `brand.name`, `image`,
`sku` (13-значный ВНУТРЕННИЙ код — store_article, НЕ артикул производителя,
тот же вывод, что и в tools/harvest/stores/magazin01.py) — разбор ОБЩИМ
хелпером price_from_product_page (ПРАВИЛО №6, не вторая копия JSON-LD
парсинга).

Довизит — ТОЛЬКО для первых MAX_PRODUCT_VISITS результатов (бюджет
параллельных довизитов одного запроса, см. docstring service.py) — остальные
результаты поиска отбрасываются (без цены предложение не несёт пользы для
сравнения, лучше показать МЕНЬШЕ, но с ценой)."""
from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import quote

from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name
from app.services.store_search.price_from_product_page import extract_price_and_image

STORE_KEY = "magazin01"
DOMAIN = "magazin01.ru"
STORE_NAME_FALLBACK = "Магазин 01"
BASE_URL = "https://magazin01.ru"

SEARCH_URL = "https://magazin01.ru/search/?q={q}"
MAX_PRODUCT_VISITS = 5

_RESULT_LINK_RE = re.compile(r'<a\s+href="(/product/[^"#?]+)[^"]*">([\s\S]*?)</a>')
_TAG_RE = re.compile(r"<[^>]+>")


def parse_search_html_links(html: str) -> list[tuple[str, str]]:
    """(url, name) пары из текстового списка результатов — только товарные
    ссылки (`/product/...`), без цены (см. docstring модуля)."""
    out: list[tuple[str, str]] = []
    seen: set = set()
    if not html:
        return out
    for rel_url, inner in _RESULT_LINK_RE.findall(html):
        if rel_url in seen:
            continue
        seen.add(rel_url)
        name = _TAG_RE.sub("", inner).strip()
        if name:
            out.append((BASE_URL + rel_url, name))
    return out


class Magazin01Adapter:
    key = STORE_KEY
    domain = DOMAIN

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        url = SEARCH_URL.format(q=quote(query))
        html = await client.get_text(url)
        if not html:
            return []
        links = parse_search_html_links(html)[:MAX_PRODUCT_VISITS]
        if not links:
            return []

        product_urls = [u for u, _ in links]
        pages = await client.get_many(product_urls)

        offers: list[StoreOffer] = []
        for (product_url, fallback_name), page_html in zip(links, (pages.get(u) for u in product_urls)):
            if not page_html:
                continue
            price, image = extract_price_and_image(page_html)
            name, manufacturer, sku = _parse_product_meta(page_html, fallback_name)
            offers.append(StoreOffer(
                store_key=STORE_KEY,
                store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
                seller_inn=seller_inn_for_domain(DOMAIN),
                name=name,
                price=price,
                url=product_url,
                image_url=image,
                store_article=sku,
                manufacturer=manufacturer,
            ))
        return offers[:limit]


_LDJSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>([\s\S]*?)</script>', re.IGNORECASE)


def _parse_product_meta(html: str, fallback_name: str) -> tuple[str, Optional[str], Optional[str]]:
    for block in _LDJSON_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            name = data.get("name") or fallback_name
            brand = data.get("brand")
            manufacturer = brand.get("name") if isinstance(brand, dict) else (brand if isinstance(brand, str) else None)
            sku = str(data.get("sku")).strip() if data.get("sku") else None
            return name, manufacturer, sku
    return fallback_name, None, None
