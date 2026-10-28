"""Адаптер живого поиска sima-land.ru — этап 1 «живой поиск товара в
магазинах», владелец, 28.10.2026.

Проверено на живой фикстуре (backend/tests/fixtures/store_search/sima_land.json,
запрос «перчатки», `?q=<query>&page=1&per-page=N`): Accept: application/json
отдаёт тот же JSON API, что и у категорий (tools/harvest/stores/sima_land.py
::parse_category_page — та же форма `{"items": [...]}`, другой параметр
запроса) — НЕ XML, вопреки опасению в задании. Поля те же: `name`, `sid`
(store_article), `itemUrl`, `price`, `trademark.name` (бренд; на этой
фикстуре у части товаров `trademark` — явный `null`, не только отсутствует
ключ), `country.name`, изображение — `photoUrl` ИЛИ (если его нет в ответе
поиска) `img` (НЕ дублирующий источник — одно и то же поле под разными
именами у разных форм sima-land API, Правило №6: берём первое найденное,
второй параллельный список фото не считаем)."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name

STORE_KEY = "sima_land"
DOMAIN = "sima-land.ru"
STORE_NAME_FALLBACK = "Сима-ленд"

SEARCH_URL = "https://www.sima-land.ru/api/v3/item/?q={q}&page=1&per-page={limit}"


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
    for item in (data.get("items") or []):
        name = (item.get("name") or "").strip()
        sid = item.get("sid")
        if not name or not sid:
            continue
        item_url = item.get("itemUrl")
        url = f"https://www.sima-land.ru{item_url}" if item_url else f"https://www.sima-land.ru/{sid}/"
        trademark = item.get("trademark") or {}
        country = item.get("country") or {}
        image = item.get("photoUrl") or item.get("img")
        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
            seller_inn=seller_inn_for_domain(DOMAIN),
            name=name,
            price=_decimal(item.get("price")),
            url=url,
            image_url=image if isinstance(image, str) else None,
            store_article=str(sid),
            manufacturer=(trademark.get("name") or "").strip() or None,
        ))
    return offers


class SimaLandAdapter:
    key = STORE_KEY
    domain = DOMAIN

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        url = SEARCH_URL.format(q=quote(query), limit=limit)
        raw = await client.get_text(url, headers={"Accept": "application/json"})
        if not raw:
            return []
        return parse_search_json(raw)[:limit]
