"""Адаптер живого поиска avtoall.ru — вторая волна «живого поиска товара в
магазинах», владелец, 28.10.2026.

Проверено живыми запросами этой сессии (backend/tests/fixtures/store_search/
avtoall.json, запрос «масло 5w40»): `GET https://www.avtoall.ru/search/
global/?term=<q>` отдаёт `{"status":"fail"}` БЕЗ заголовков `Referer:
https://www.avtoall.ru/` + `X-Requested-With: XMLHttpRequest` (анти-бот по
источнику XHR, та же идея, что у regard.py) — С заголовками отдаёт
`{"status":"success","data":[{"name","avgPrice","picUrl","value",
"isCategory"}]}`. `isCategory=true` — это подсказка-категория, не товар,
пропускается.

Ссылка на товар: `value` — строка вида "<id>;;" (внутренний id предложения,
без категории/магазина-продавца в самом значении). Проверено отдельным живым
запросом (SSR-страница `/search/?GlobalFilterForm...`) — она не содержит
прямых ссылок на карточки товара по этому id (список рендерится клиентским
JS отдельным запросом, не найденным в бюджете живых запросов этой сессии).
Поэтому, как и предписано заданием («если нельзя — ссылка на страницу
поиска магазина с этим запросом»), url ВСЕХ предложений — страница поиска
avtoall.ru с тем же запросом, не карточка конкретного товара."""
from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name

STORE_KEY = "avtoall"
DOMAIN = "avtoall.ru"
STORE_NAME_FALLBACK = "AvtoAll"
BASE_URL = "https://www.avtoall.ru"

SEARCH_URL = "https://www.avtoall.ru/search/global/?term={q}"

_PRICE_DIGITS_RE = re.compile(r"[\d\s]+")


def _decimal_from_price_text(text: Optional[str]) -> Optional[Decimal]:
    if not text:
        return None
    m = _PRICE_DIGITS_RE.search(text)
    if not m:
        return None
    digits = re.sub(r"\s", "", m.group(0))
    if not digits:
        return None
    try:
        return Decimal(digits)
    except Exception:
        return None


def parse_search_json(raw: str, query: str) -> list[StoreOffer]:
    offers: list[StoreOffer] = []
    if not raw:
        return offers
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return offers
    if data.get("status") != "success":
        return offers
    # Ссылка на поиск — общая для всех предложений этого ответа (см. docstring),
    # тот же путь, что разведка видела в финальном URL SSR-страницы поиска.
    search_page_url = f"{BASE_URL}/search/?GlobalFilterForm%5Bnamearticle%5D={quote(query)}"
    for item in (data.get("data") or []):
        if item.get("isCategory"):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        pic = item.get("picUrl")
        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
            seller_inn=seller_inn_for_domain(DOMAIN),
            name=name,
            price=_decimal_from_price_text(item.get("avgPrice")),
            url=search_page_url,
            image_url=(f"{BASE_URL}{pic}" if isinstance(pic, str) and pic.startswith("/") else None),
            store_article=(item.get("value") or "").split(";")[0] or None,
        ))
    return offers


class AvtoallAdapter:
    key = STORE_KEY
    domain = DOMAIN

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        url = SEARCH_URL.format(q=quote(query))
        raw = await client.get_text(url, headers={
            "Accept": "application/json",
            "Referer": BASE_URL + "/",
            "X-Requested-With": "XMLHttpRequest",
        })
        if not raw:
            return []
        return parse_search_json(raw, query)[:limit]
