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
from html import unescape as _html_unescape
from typing import Optional
from urllib.parse import quote

from app.services.store_search.base import StoreOffer, seller_inn_for_domain, store_display_name

STORE_KEY = "avtoall"
DOMAIN = "avtoall.ru"
STORE_NAME_FALLBACK = "AvtoAll"
BASE_URL = "https://www.avtoall.ru"

SEARCH_URL = "https://www.avtoall.ru/search/global/?term={q}"
SSR_SEARCH_URL = "https://www.avtoall.ru/search/?GlobalFilterForm%5Bnamearticle%5D={q}"

_PRICE_DIGITS_RE = re.compile(r"[\d\s]+")
_SSR_ITEM_BLOCK_RE = re.compile(
    r'<div class="item item-elem product-item"[\s\S]*?'
    r'(?=<div class="item item-elem product-item"|<div class="notes"|<div class="pagination"|$)'
)
_SSR_NAME_RE = re.compile(r'<strong class="item-name">\s*<a href="([^"]+)">([\s\S]*?)</a>', re.IGNORECASE)
_SSR_PRICE_RE = re.compile(r'<b class="price-internet">([\s\S]*?)</b>', re.IGNORECASE)
_SSR_CODE_RE = re.compile(r'data-good-code="(\d+)"|Код для заказа:\s*(\d+)', re.IGNORECASE)
_SSR_MFG_ARTICLE_RE = re.compile(r"<b>\s*Артикул:\s*([^<\s]+)", re.IGNORECASE)
_SSR_MFG_RE = re.compile(r'Производитель:\s*([^<\n•]+)', re.IGNORECASE)
_SSR_DATA_SRC_RE = re.compile(r'<img[^>]+data-src="([^"]+)"', re.IGNORECASE)
_SSR_SRC_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_DECIMAL_UNIT_RELAX_RE = re.compile(
    r"(\d+)[.,](\d+)\s*(?:мм|см|м|кг|г|л|мл)(?![a-zа-яё0-9])",
    re.IGNORECASE,
)


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


def parse_search_html(html: str) -> list[StoreOffer]:
    """Разбор полнотекстовой SSR-страницы поиска avtoall.ru
    (`/search/?GlobalFilterForm[namearticle]=<q>`). Возвращает карточки с
    прямыми ссылками на товар, полными названиями, интернет-ценой, кодом
    магазина и производителем. В отличие от быстрых подсказок `/search/global/`,
    SSR-поиск ищет по полным названиям моделей ('Hakkapeliitta', 'Nordman') и
    сам исправляет опечатки ('hakkapelitta' → 'hakkapeliitta')."""
    offers: list[StoreOffer] = []
    if not html:
        return offers
    store_name = store_display_name(DOMAIN, STORE_NAME_FALLBACK)
    seller_inn = seller_inn_for_domain(DOMAIN)
    seen_urls: set[str] = set()
    for block in _SSR_ITEM_BLOCK_RE.findall(html):
        name_m = _SSR_NAME_RE.search(block)
        if not name_m:
            continue
        rel_url = name_m.group(1).strip()
        name = _html_unescape(_TAG_RE.sub("", name_m.group(2))).strip()
        if not name or not rel_url:
            continue
        full_url = f"{BASE_URL}{rel_url}" if rel_url.startswith("/") else rel_url
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        mfg_art_m = _SSR_MFG_ARTICLE_RE.search(block)
        if mfg_art_m:
            mfg_art = _html_unescape(mfg_art_m.group(1)).strip().rstrip(",;.")
            if mfg_art and mfg_art.lower() not in name.lower():
                name = f"{name} {mfg_art}"

        price_m = _SSR_PRICE_RE.search(block)
        price = _decimal_from_price_text(_TAG_RE.sub("", price_m.group(1)) if price_m else None)

        code_m = _SSR_CODE_RE.search(block)
        store_article = (code_m.group(1) or code_m.group(2)) if code_m else None

        mfg_m = _SSR_MFG_RE.search(block)
        manufacturer = mfg_m.group(1).strip() if mfg_m else None

        img_url = None
        img_m = _SSR_DATA_SRC_RE.search(block) or _SSR_SRC_RE.search(block)
        if img_m:
            raw_img = img_m.group(1).strip()
            if raw_img and "loader-vue" not in raw_img:
                img_url = f"{BASE_URL}{raw_img}" if raw_img.startswith("/") else raw_img

        offers.append(StoreOffer(
            store_key=STORE_KEY,
            store_name=store_name,
            seller_inn=seller_inn,
            name=name,
            price=price,
            url=full_url,
            image_url=img_url,
            manufacturer=manufacturer,
            store_article=store_article,
        ))
    return offers


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
    display_name = STORE_NAME_FALLBACK

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        ssr_url = SSR_SEARCH_URL.format(q=quote(query))
        ssr_html = await client.get_text(ssr_url)
        if ssr_html:
            ssr_offers = parse_search_html(ssr_html)
            if ssr_offers:
                return ssr_offers[:limit]
        relaxed_q = _DECIMAL_UNIT_RELAX_RE.sub(r"\1.\2", query)
        if relaxed_q != query:
            rel_html = await client.get_text(SSR_SEARCH_URL.format(q=quote(relaxed_q)))
            if rel_html:
                rel_offers = parse_search_html(rel_html)
                if rel_offers:
                    return rel_offers[:limit]
        url = SEARCH_URL.format(q=quote(query))
        raw = await client.get_text(url, headers={
            "Accept": "application/json",
            "Referer": BASE_URL + "/",
            "X-Requested-With": "XMLHttpRequest",
        })
        if not raw:
            return []
        return parse_search_json(raw, query)[:limit]
