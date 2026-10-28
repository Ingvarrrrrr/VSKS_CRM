"""Адаптер живого поиска regard.ru — вторая волна «живого поиска товара в
магазинах», владелец, 28.10.2026. Правка 29.10.2026 (QA живого поиска) —
ссылка на карточку товара заменена на страницу поиска, см. ниже.

Проверено живым запросом (разведка браузером + прямые запросы этой сессии,
backend/tests/fixtures/store_search/regard.json, запрос «монитор»):
`POST https://www.regard.ru/api/site/goods/list` с телом `{"start":0,
"length":24,"showCategories":true,"scope":{"orderByPopularity":"desc",
"search":"<q>"}}` — заголовки Referer/Origin https://www.regard.ru ОБЯЗАТЕЛЬНЫ
(без них сайт отвечает `title/vendor` ИЛИ вовсе другой страницей; как и у
avtoall.py — next.js фронт отличает «свой» XHR по Referer, не только по
Accept). Ответ `{"data":[{...}]}` — `title`/`price`/`vendor`/`vendorcode`/
`photo` (относительный путь, например "/6602409")/`seo_url`.

Ссылка на товар: страница `/catalog/<seo_url>` (конвенция Next.js каталога
этого сайта) ПРОВЕРЕНА прямым GET этой сессии (обычный UA, без cookie
браузера) на реальном seo_url из живого ответа ("monitor-xiaomi-27-a27i-2026")
— сайт вернул 200, но редиректнул (`follow_redirects`) на `/catalog/all`
(общий каталог, НЕ карточка товара) — анти-бот/геолокационная защита
Next.js middleware режет прямые запросы без сессии браузера так же, как у
avtoall.ru, подтверждённого факта. Раз прямая ссылка на карточку не
открывается без браузерной сессии — ссылка строится на страницу ПОИСКА
`https://www.regard.ru/catalog?search=<query>` (та же, что finalUrl разведки
`regard.ru/catalog?search=...`), с исходным запросом пользователя (не
названием товара — у магазина нет публичного URL карточки без браузера);
эта страница ПРОВЕРЕНА прямым GET этой сессии — отвечает 200 без редиректа.

photo → image_url: прямой GET этой сессии на `{BASE_URL}{photo}` (например
https://www.regard.ru/6602409) вернул 404 — это НЕ CDN-путь картинки, а
что-то другое (внутренний id/заглушка); абсолютный CDN-домен для фото в
разведке не встретился ни в одном перехваченном запросе — image_url
по-прежнему НЕ строим (признанно неизвестно, не выдумываем)."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name

STORE_KEY = "regard"
DOMAIN = "regard.ru"
STORE_NAME_FALLBACK = "Регард"
BASE_URL = "https://www.regard.ru"

SEARCH_URL = "https://www.regard.ru/api/site/goods/list"


def _decimal(raw) -> Optional[Decimal]:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


def _search_page_url(query: str) -> str:
    """Ссылка на страницу поиска regard.ru — используется для КАЖДОГО
    предложения вместо прямой ссылки на карточку (см. докстринг модуля:
    карточка без браузерной сессии недоступна, страница поиска открывается
    всегда и ведёт к тому же товару в списке)."""
    return f"{BASE_URL}/catalog?search={quote((query or '').strip())}"


def parse_search_json(raw: str, query: str = "") -> list[StoreOffer]:
    offers: list[StoreOffer] = []
    if not raw:
        return offers
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return offers
    url = _search_page_url(query)
    for item in (data.get("data") or []):
        title = (item.get("title") or "").strip()
        seo_url = item.get("seo_url")
        if not title or not seo_url:
            continue
        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
            seller_inn=seller_inn_for_domain(DOMAIN),
            name=title,
            price=_decimal(item.get("price")),
            url=url,
            image_url=None,
            store_article=str(item.get("id")) if item.get("id") is not None else None,
            manufacturer=(item.get("vendor") or "").strip() or None,
        ))
    return offers


class RegardAdapter:
    key = STORE_KEY
    domain = DOMAIN

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        body = json.dumps({
            "start": 0, "length": limit, "showCategories": True,
            "scope": {"orderByPopularity": "desc", "search": query},
        })
        raw = await client.post_text(
            SEARCH_URL, body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Referer": BASE_URL + "/",
                "Origin": BASE_URL,
            },
        )
        if not raw:
            return []
        return parse_search_json(raw, query=query)[:limit]
