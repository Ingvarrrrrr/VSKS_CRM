"""Адаптер живого поиска safe.ru (завод ПРОМЕТ) — этап 1 «живой поиск товара
в магазинах», владелец, 28.10.2026.

Проверено на живой фикстуре (backend/tests/fixtures/store_search/safe.html,
запрос «шкаф»): результаты поиска — Bitrix-карточки
`<div class="tile-card" itemprop="itemListElement" itemscope
itemtype="http://schema.org/Product"> <link itemprop="url" href="...">
<meta itemprop="brand" content="...">` ... `<a class="tile-card__title"
itemprop="name">Название</a>` ... цена — ТЕКСТ внутри
`<div class="tile-card__price" itemprop="offers" ...>` (meta itemprop="price"
сам пустой на живой фикстуре, настоящее число — в видимом тексте "23 050
руб.", НЕ в атрибуте — как и предупреждал владелец про регекс по тексту "руб"
у старого сборщика: здесь это НЕ угадывание, а единственный источник,
который реально несёт число). store_article — `data-id` на кнопке "В список
покупок" (тот же паттерн, что и tools/harvest/stores/safe.py на странице
товара).

НЕ каждая карточка результата поиска — товар с ценой: часть карточек
(подкатегории типа «Шкафы инструментальные TC-1995», без itemtype=Product)
ведут на листовой раздел, не на товар, — такие карточки пропускаются."""
from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import quote

from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name

STORE_KEY = "safe"
DOMAIN = "safe.ru"
STORE_NAME_FALLBACK = "Safe.ru (ПРОМЕТ)"

SEARCH_URL = "https://www.safe.ru/search/?q={q}"

_CARD_SPLIT_RE = re.compile(r'class="catalog__card[^"]*catalog__card--search[^"]*"')
_PRODUCT_CARD_RE = re.compile(r'itemtype="http://schema\.org/Product"')
_URL_RE = re.compile(r'itemprop="url"\s+href="([^"]+)"')
_BRAND_RE = re.compile(r'itemprop="brand"\s+content="([^"]*)"')
_NAME_RE = re.compile(r'itemprop="name"[^>]*>([^<]*)</a>')
_PRICE_BLOCK_RE = re.compile(r'class="tile-card__price"[\s\S]*?</div>')
_PRICE_NUM_RE = re.compile(r'([\d\s]{2,})\s*руб')
_DATA_ID_RE = re.compile(r'data-id="(\d+)"')
_IMG_RE = re.compile(r'<img\s+src="([^"]+)"')


def parse_search_html(html: str) -> list[StoreOffer]:
    offers: list[StoreOffer] = []
    if not html:
        return offers
    for raw_card in _CARD_SPLIT_RE.split(html)[1:]:
        # Карточка-подкатегория (без Product microdata) — не товар, пропуск.
        if not _PRODUCT_CARD_RE.search(raw_card[:400]):
            continue
        card = raw_card[:4000]
        url_m = _URL_RE.search(card)
        name_m = _NAME_RE.search(card)
        if not url_m or not name_m:
            continue
        url = url_m.group(1)
        name = name_m.group(1).strip()
        if not name or not url:
            continue
        price = None
        price_block_m = _PRICE_BLOCK_RE.search(card)
        if price_block_m:
            num_m = _PRICE_NUM_RE.search(price_block_m.group(0))
            if num_m:
                digits = re.sub(r"\s", "", num_m.group(1))
                if digits:
                    price = Decimal(digits)
        brand_m = _BRAND_RE.search(card)
        manufacturer = brand_m.group(1).strip() if brand_m and brand_m.group(1).strip() else None
        data_id_m = _DATA_ID_RE.search(card)
        img_m = _IMG_RE.search(card)
        image = img_m.group(1) if img_m else None
        if image and image.startswith("/"):
            image = "https://www.safe.ru" + image
        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
            seller_inn=seller_inn_for_domain(DOMAIN),
            name=name,
            price=price,
            url=url,
            image_url=image,
            store_article=data_id_m.group(1) if data_id_m else None,
            manufacturer=manufacturer,
        ))
    return offers


class SafeAdapter:
    key = STORE_KEY
    domain = DOMAIN

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        url = SEARCH_URL.format(q=quote(query))
        html = await client.get_text(url)
        if not html:
            return []
        return parse_search_html(html)[:limit]
