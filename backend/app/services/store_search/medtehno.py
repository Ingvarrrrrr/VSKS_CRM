"""Адаптер живого поиска medtehno.ru — вторая волна «живого поиска товара в
магазинах», владелец, 28.10.2026.

Проверено живым запросом разведки (backend/tests/fixtures/store_search/
medtehno.json, запрос «аптечка», 20 из 109 найденных): поиск этого магазина
отдаёт стороннему сервису `GET https://sort.diginetica.net/search?st=<q>&
apiKey=K46ZVWQYWV&strategy=advanced_xname,zero_queries&fullData=true&
size=20&offset=0&sort=DEFAULT`. apiKey — ПУБЛИЧНЫЙ ключ виджета поиска этого
сайта (виден в открытом JS-запросе любому посетителю страницы medtehno.ru,
не секрет продавца — то же, чем Diginetica продаёт свой сервис поиска
десяткам магазинов под их собственными публичными ключами); константа здесь,
не секрет окружения.

Ответ — `{"products":[{...}], "totalHits": N}` — `name`/`brand`/`price`
(строка, напр. "990.0")/`link_url` (относительный путь magazin'а, ОТКРЫВАЕТСЯ
на medtehno.ru, не diginetica)/`image_url`."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name

STORE_KEY = "medtehno"
DOMAIN = "medtehno.ru"
STORE_NAME_FALLBACK = "Промедик (medtehno.ru)"
BASE_URL = "https://www.medtehno.ru"

# Публичный apiKey поискового виджета Diginetica на medtehno.ru (см. docstring
# модуля) — не секрет окружения, виден в открытом запросе страницы сайта.
_DIGINETICA_API_KEY = "K46ZVWQYWV"
SEARCH_URL = (
    "https://sort.diginetica.net/search?st={q}&apiKey=" + _DIGINETICA_API_KEY
    + "&strategy=advanced_xname,zero_queries&fullData=true&size={limit}&offset=0&sort=DEFAULT"
)


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
        name = (item.get("name") or "").strip()
        link_url = item.get("link_url")
        if not name or not link_url:
            continue
        url = link_url if link_url.startswith("http") else f"{BASE_URL}{link_url}"
        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
            seller_inn=seller_inn_for_domain(DOMAIN),
            name=name,
            price=_decimal(item.get("price")),
            url=url,
            image_url=item.get("image_url") if isinstance(item.get("image_url"), str) else None,
            store_article=str(item.get("id")) if item.get("id") is not None else None,
            manufacturer=(item.get("brand") or "").strip() or None,
        ))
    return offers


class MedtehnoAdapter:
    key = STORE_KEY
    domain = DOMAIN

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        url = SEARCH_URL.format(q=quote(query), limit=limit)
        raw = await client.get_text(url, headers={"Accept": "application/json"})
        if not raw:
            return []
        return parse_search_json(raw)[:limit]
