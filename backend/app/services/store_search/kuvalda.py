"""Адаптер живого поиска kuvalda.ru (этап 1 «живой поиск товара в
магазинах», владелец, 28.10.2026). Разбор — ТОЛЬКО HTML-ответ страницы
поиска; запросы/кэш/лимит частоты — service.py (ПРАВИЛО №5/№6, тот же
принцип разделения, что у tools/harvest/stores/*.py).

Проверено на живой фикстуре (backend/tests/fixtures/store_search/kuvalda.html,
запрос «перфоратор», редиректит на /catalog/<id>-perforatory/?keyword=...):
HTML несёт JSON-LD `"@type":"OfferCatalog"` с `itemListElement` — те же
name/url/price/image, что и на обычной странице раздела (см.
tools/harvest/stores/kuvalda.py::parse_category_page — та же форма ответа,
другой URL, второй разбор HTML здесь НЕ пишем, только адаптируем под
StoreOffer)."""
from __future__ import annotations

import json
import re
from decimal import Decimal
from urllib.parse import quote

from app.services.store_search.base import (
    StoreBlocked, StoreOffer, seller_inn_for_domain, store_display_name,
)

STORE_KEY = "kuvalda"
DOMAIN = "kuvalda.ru"
STORE_NAME_FALLBACK = "Кувалда.ру"

SEARCH_URL = "https://www.kuvalda.ru/catalog/search/?keyword={q}"

_JSONLD_RE = re.compile(r'<script\s+type="application/ld\+json"[^>]*>([\s\S]*?)</script>')

# Диагностика с прода 29.10.2026 (owner-жалоба — kuvalda.ru всегда 0): живой
# запрос из контейнера backend_a дал 200 и валидный OfferCatalog (см. отчёт
# сессии) — блокировки по IP прода на момент проверки НЕТ, антибот-маркеры
# ниже на живом ответе не встретились. Оставлены как защита на будущее
# (ПРАВИЛО №8 п.6): если kuvalda включит JS-челлендж/капчу, страница обычно
# всё равно отдаётся с HTTP 200 (service.py::get_text иначе вернул бы None
# и parse_search_html просто не нашёл бы OfferCatalog, что неотличимо от
# честных «0 найдено» — см. StoreBlocked в base.py).
_BLOCK_MARKERS = (
    "cf-browser-verification",
    "checking your browser",
    "id=\"challenge-form\"",
    "attention required",
    "qrator",
    "доступ ограничен",
    "access denied",
    "captcha",
)


def _looks_blocked(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in _BLOCK_MARKERS)


def _find_offer_catalog(html: str) -> dict:
    for block in _JSONLD_RE.findall(html):
        try:
            obj = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("@type") == "OfferCatalog":
            return obj
    return {}


def parse_search_html(html: str) -> list[StoreOffer]:
    catalog = _find_offer_catalog(html)
    offers: list[StoreOffer] = []
    for offer in catalog.get("itemListElement", []):
        url = offer.get("url")
        name = offer.get("name")
        if not url or not name:
            continue
        price_raw = offer.get("price")
        price = Decimal(str(price_raw)) if price_raw else None
        image = offer.get("image")
        store_article_m = re.search(r"product-(\d+)", url)
        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
            seller_inn=seller_inn_for_domain(DOMAIN),
            name=name,
            price=price,
            url=url,
            image_url=image if isinstance(image, str) and image.startswith("http") else None,
            store_article=store_article_m.group(1) if store_article_m else None,
        ))
    return offers


class KuvaldaAdapter:
    key = STORE_KEY
    domain = DOMAIN
    display_name = STORE_NAME_FALLBACK

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        url = SEARCH_URL.format(q=quote(query))
        html = await client.get_text(url)
        if not html:
            return []
        if _looks_blocked(html):
            raise StoreBlocked(f"{DOMAIN}: антибот-страница вместо результатов поиска")
        return parse_search_html(html)[:limit]
