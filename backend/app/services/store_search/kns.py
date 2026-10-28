"""Адаптер живого поиска kns.ru — вторая волна «живого поиска товара в
магазинах», владелец, 28.10.2026.

Проверено живым запросом этой сессии (backend/tests/fixtures/store_search/
kns.html, запрос «монитор»): `GET https://www.kns.ru/search.html?s_word=<q>`
— если запрос однозначно совпал с категорией (как «монитор»), Bitrix 302-
редиректит на `/catalog/<категория>/` (разведка браузером это тоже видела —
finalUrl там остался на корне, значит сам поиск клиентским JS подгружается
отдельно, а прямой GET честно делает редирект). И на редиректнутой странице
категории, и на НЕредиректнутой выдаче поиска разметка карточки ОДНА и та
же (общий шаблон каталога Bitrix) — `follow_redirects=True` в HTTP-клиенте
(service.py) уже обрабатывает это прозрачно, адаптер просто разбирает HTML
ответа, какой бы URL ни стал финальным.

Карточка — `<div class="goods-item" itemscope itemtype="schema.org/Product">`:
`<a href="/product/<slug>/" itemprop="url">`, `<img src=... itemprop="image">`,
`<span itemprop="name">Название</span>`, `<span itemprop="sku">КОД</span>`,
цена — `<span class="goods-price1">ЧИСЛО</span>` внутри `price-current`."""
from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import quote

from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name

STORE_KEY = "kns"
DOMAIN = "kns.ru"
STORE_NAME_FALLBACK = "КНС (kns.ru)"
BASE_URL = "https://www.kns.ru"

SEARCH_URL = "https://www.kns.ru/search.html?s_word={q}"

_CARD_SPLIT_RE = re.compile(r'class="goods-item[^"]*"\s+itemscope="itemscope"\s+itemtype="http://schema\.org/Product"')
_URL_RE = re.compile(r'<a\s+href="(/product/[^"#?]+)"[^>]*\bitemprop="url"')
_IMG_RE = re.compile(r'<img[^>]*\bsrc="([^"]+)"[^>]*\bitemprop="image"')
_NAME_RE = re.compile(r'<span\s+itemprop="name">([^<]*)</span>')
_SKU_RE = re.compile(r'<span\s+class="goods-code"\s+itemprop="sku">([^<]*)</span>')
_PRICE_RE = re.compile(r'class="[^"]*\bgoods-price1\b[^"]*">\s*([\d\s]+)\s*</span>')


def parse_search_html(html: str) -> list[StoreOffer]:
    offers: list[StoreOffer] = []
    if not html:
        return offers
    cards = _CARD_SPLIT_RE.split(html)[1:]
    for raw_card in cards:
        card = raw_card[:4000]
        url_m = _URL_RE.search(card)
        name_m = _NAME_RE.search(card)
        if not url_m or not name_m:
            continue
        name = name_m.group(1).strip()
        if not name:
            continue
        price = None
        price_m = _PRICE_RE.search(card)
        if price_m:
            digits = re.sub(r"\s", "", price_m.group(1))
            if digits:
                price = Decimal(digits)
        img_m = _IMG_RE.search(card)
        sku_m = _SKU_RE.search(card)
        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
            seller_inn=seller_inn_for_domain(DOMAIN),
            name=name,
            price=price,
            url=BASE_URL + url_m.group(1),
            image_url=img_m.group(1) if img_m else None,
            store_article=sku_m.group(1).strip() if sku_m else None,
        ))
    return offers


class KnsAdapter:
    key = STORE_KEY
    domain = DOMAIN

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        url = SEARCH_URL.format(q=quote(query))
        html = await client.get_text(url)
        if not html:
            return []
        return parse_search_html(html)[:limit]
