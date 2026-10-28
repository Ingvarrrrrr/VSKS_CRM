"""Адаптер живого поиска emex.ru — вторая волна «живого поиска товара в
магазинах», владелец, 28.10.2026.

emex.ru ищет ТОЛЬКО по номеру детали (артикулу производителя) — проверено
живыми запросами этой сессии: свободный текст («масло 5w40», разведка
браузером) → `{"searchResult":{"noResults":true}}`; настоящий артикул
(«0510000410», backend/tests/fixtures/store_search/emex.json) → список
предложений с ценой. Поэтому адаптер включается ТОЛЬКО когда запрос похож
на артикул — ПЕРЕИСПОЛЬЗУЕТ app.services.product_search._looks_like_
article_query (ПРАВИЛО №6, тот же признак «один токен без пробелов с хотя
бы одной цифрой», что и у встроенного поиска по своей базе для того же
решения «это похоже на код/артикул, не на обычные слова»; второй такой
признак не заводим) — service.py зовёт search() только после этой проверки
(см. registry.py::ARTICLE_ONLY_STORES).

`GET https://emex.ru/api/search/search2?detailNum=<q>&isHeaderSearch=true&
showAll=false&searchSource=direct&searchString=<q>` → `{"searchResult":
{"num","name","makes":{"list":[{"make","name","url","bestPrice":{"value"}}
]}}}`. `url` — относительный `/<num>/<make-slug>` (полный URL — BASE_URL +
url). Поле image в ответе НЕТ ни у одной записи — image_url остаётся None
(не выдумываем). `name` элемента списка иногда пустой (только у
`identificationProductGroupId`-варианта без собственного названия, см.
фикстуру) — в этом случае берём верхнеуровневое `searchResult.name`
(название САМОЙ детали по артикулу, то же для всех предложений)."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from app.services.product_search import _looks_like_article_query
from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name

STORE_KEY = "emex"
DOMAIN = "emex.ru"
STORE_NAME_FALLBACK = "Emex"
BASE_URL = "https://emex.ru"

SEARCH_URL = (
    "https://emex.ru/api/search/search2?detailNum={q}&isHeaderSearch=true"
    "&showAll=false&searchSource=direct&searchString={q}"
)

# Переиспользуем ПРИЗНАК "похоже на артикул" у встроенного поиска (см.
# docstring модуля) — service.py зовёт эту функцию перед обращением к
# адаптеру, чтобы не тратить запрос впустую на обычный текстовый запрос.
looks_like_article_query = _looks_like_article_query


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
    result = data.get("searchResult") or {}
    if result.get("noResults") or not result.get("makes"):
        return offers
    fallback_name = (result.get("name") or "").strip()
    for item in (result.get("makes", {}).get("list") or []):
        name = (item.get("name") or "").strip() or fallback_name
        url_path = item.get("url")
        if not name or not url_path:
            continue
        best_price = item.get("bestPrice") or {}
        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
            seller_inn=seller_inn_for_domain(DOMAIN),
            name=name,
            price=_decimal(best_price.get("value")),
            url=f"{BASE_URL}{url_path}" if url_path.startswith("/") else url_path,
            manufacturer=(item.get("make") or "").strip() or None,
        ))
    return offers


class EmexAdapter:
    key = STORE_KEY
    domain = DOMAIN

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        if not looks_like_article_query(query):
            return []
        url = SEARCH_URL.format(q=quote(query))
        raw = await client.get_text(url, headers={"Accept": "application/json"})
        if not raw:
            return []
        return parse_search_json(raw)[:limit]
