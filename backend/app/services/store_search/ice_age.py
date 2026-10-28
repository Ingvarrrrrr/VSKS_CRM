"""Адаптер живого поиска ice-age.ru (InSales) — вторая волна «живого поиска
товара в магазинах», владелец, 28.10.2026.

Проверено прямым живым запросом этой сессии (backend/tests/fixtures/
store_search/ice_age.json, запрос «перчатки», 13 найденных): `GET https://
ice-age.ru/collection/catalog.json?lang=ru&q=<q>` отдаёт сразу `{"status":
"ok","count":N,"products":[{...}]}` — ПОЛНЫЕ карточки (title/url/price_min/
images/variants[].price), визит на отдельный `/products_by_id/<ids>.json`
(как это делает сам сайт в браузере после SSR-страницы каталога) НЕ нужен —
тот же результат отдаёт один прямой JSON-запрос."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name

STORE_KEY = "ice_age"
DOMAIN = "ice-age.ru"
STORE_NAME_FALLBACK = "ICE AGE"
BASE_URL = "https://ice-age.ru"

SEARCH_URL = "https://ice-age.ru/collection/catalog.json?lang=ru&q={q}"


def _decimal(raw) -> Optional[Decimal]:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
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
    for item in (data.get("products") or []):
        title = (item.get("title") or "").strip()
        url_path = item.get("url")
        if not title or not url_path:
            continue
        images = item.get("images") or []
        image_url = images[0].get("medium_url") or images[0].get("url") if images else None
        # variants[0].price — настоящая цена товара (price_min может быть 0
        # у товаров без фиксированной цены варианта, см. docstring выше);
        # price_min — запасной путь, если вариантов нет вовсе.
        variants = item.get("variants") or []
        price = _decimal(variants[0].get("price")) if variants else None
        if price is None:
            price = _decimal(item.get("price_min"))
        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
            seller_inn=seller_inn_for_domain(DOMAIN),
            name=title,
            price=price,
            url=f"{BASE_URL}{url_path}" if url_path.startswith("/") else url_path,
            image_url=image_url if isinstance(image_url, str) else None,
            store_article=str(item.get("id")) if item.get("id") is not None else None,
        ))
    return offers


class IceAgeAdapter:
    key = STORE_KEY
    domain = DOMAIN

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        url = SEARCH_URL.format(q=quote(query))
        raw = await client.get_text(url, headers={"Accept": "application/json"})
        if not raw:
            return []
        return parse_search_json(raw)[:limit]
