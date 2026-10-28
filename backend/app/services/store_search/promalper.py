"""Адаптер живого поиска promalper.com — этап 1 «живой поиск товара в
магазинах», владелец, 28.10.2026.

Проверено на живой фикстуре (backend/tests/fixtures/store_search/
promalper.json, запрос «карабин»): `/wp-json/premmerce-search/v1/search?q=`
отдаёт JSON-список `[{"label","link","image","price"}, ...]` — ВАЖНОЕ
отличие от предположения в задании: `price` здесь НЕ отсутствует, это ГОТОВЫЙ
HTML-фрагмент WooCommerce (`<span class="woocommerce-Price-amount
amount">...21 200&nbsp;...`), а не число — число извлекается regex'ом прямо
из этого HTML, довизит на страницу товара (price_from_product_page) ПОЭТОМУ
НЕ нужен для цены вовсе (вопреки заданию — проверено живым запросом, не
предположено). Бренд/артикул/страна в этом JSON не несутся — остаются
`None` (на отдельной странице товара они есть, см. tools/harvest/stores/
promalper.py, но довизит ради них этим этапом не делается — предложение
живого поиска показывает то, что дешёво доступно пакетно)."""
from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name

STORE_KEY = "promalper"
DOMAIN = "promalper.com"
STORE_NAME_FALLBACK = "ПромАльпер"

SEARCH_URL = "https://promalper.com/wp-json/premmerce-search/v1/search?q={q}"

_PRICE_NUM_RE = re.compile(r">\s*([\d\s]{1,}[\d])\s*&nbsp;")


def _price_from_html_fragment(fragment: Optional[str]) -> Optional[Decimal]:
    if not fragment:
        return None
    m = _PRICE_NUM_RE.search(fragment)
    if not m:
        return None
    digits = re.sub(r"\s", "", m.group(1))
    if not digits:
        return None
    try:
        return Decimal(digits)
    except Exception:
        return None


def parse_search_json(raw: str) -> list[StoreOffer]:
    offers: list[StoreOffer] = []
    if not raw:
        return offers
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return offers
    if not isinstance(data, list):
        return offers
    for item in data:
        name = (item.get("label") or "").strip()
        url = item.get("link")
        if not name or not url:
            continue
        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
            seller_inn=seller_inn_for_domain(DOMAIN),
            name=name,
            price=_price_from_html_fragment(item.get("price")),
            url=url,
            image_url=item.get("image") if isinstance(item.get("image"), str) else None,
        ))
    return offers


class PromalperAdapter:
    key = STORE_KEY
    domain = DOMAIN

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        url = SEARCH_URL.format(q=quote(query))
        raw = await client.get_text(url)
        if not raw:
            return []
        return parse_search_json(raw)[:limit]
