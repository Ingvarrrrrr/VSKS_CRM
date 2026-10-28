"""Адаптер живого поиска chipdip.ru — этап 1 «живой поиск товара в
магазинах», владелец, 28.10.2026.

Проверено на живой фикстуре (backend/tests/fixtures/store_search/chipdip.html,
запрос «резистор»): страница поиска — ТАБЛИЦА строк `<tr ... id="item<id>">`
(НЕ карточки раздела, как в tools/harvest/stores/chipdip.py::parse_category_
page — это другая форма ответа, поиск != категория у этого магазина), внутри:
`<a class="link" href="/product/<slug>">НАЗВАНИЕ (искомое слово обёрнуто в
<b>)</a>`, `Бренд:&nbsp;<span class="itemlist_pval">БРЕНД</span>`, цена —
`<span id="price_<id>">ЧИСЛО</span><span class="rub"> ₽</span>` (число —
цена за ту единицу кратности, что показана в `calc_wrap`/data-min, здесь
берётся как есть, без домножения — довизит на страницу товара для точной
цены этим заданием не делается, см. ограничение ≤3 живых запросов/магазин)."""
from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import quote

from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name

STORE_KEY = "chipdip"
DOMAIN = "chipdip.ru"
STORE_NAME_FALLBACK = "ChipDip"
BASE_URL = "https://www.chipdip.ru"

SEARCH_URL = "https://www.chipdip.ru/search?searchtext={q}"

_ROW_RE = re.compile(r'<tr[^>]*\sid="item(\d+)"[\s\S]*?</tr>\s*(?:</tr>)?', re.IGNORECASE)
_LINK_RE = re.compile(r'<a\s+class="link"\s+href="(/product/[^"#?]+)">([\s\S]*?)</a>')
_TAG_RE = re.compile(r"<[^>]+>")
_BRAND_RE = re.compile(r'itemlist_pval">([^<]*)</span>')
_PRICE_RE = re.compile(r'id="price_\d+">([^<]*)<')
_IMG_RE = re.compile(r'<img\s+src="([^"]+)"')


def parse_search_html(html: str) -> list[StoreOffer]:
    offers: list[StoreOffer] = []
    if not html:
        return offers
    for row_m in _ROW_RE.finditer(html):
        row = row_m.group(0)
        link_m = _LINK_RE.search(row)
        if not link_m:
            continue
        rel_url = link_m.group(1)
        name = _TAG_RE.sub("", link_m.group(2)).strip()
        if not name:
            continue
        brand_m = _BRAND_RE.search(row)
        price_m = _PRICE_RE.search(row)
        price = None
        if price_m:
            digits = re.sub(r"[^\d.,]", "", price_m.group(1)).replace(",", ".")
            if digits:
                try:
                    price = Decimal(digits)
                except Exception:
                    price = None
        img_m = _IMG_RE.search(row)
        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_display_name(DOMAIN, STORE_NAME_FALLBACK),
            seller_inn=seller_inn_for_domain(DOMAIN),
            name=name,
            price=price,
            url=BASE_URL + rel_url,
            image_url=img_m.group(1) if img_m else None,
            store_article=row_m.group(1),
            manufacturer=(brand_m.group(1).strip() or None) if brand_m else None,
        ))
    return offers


class ChipdipAdapter:
    key = STORE_KEY
    domain = DOMAIN

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        url = SEARCH_URL.format(q=quote(query))
        html = await client.get_text(url)
        if not html:
            return []
        return parse_search_html(html)[:limit]
