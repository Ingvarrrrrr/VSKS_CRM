"""Сборщик kuvalda.ru. Только парсинг HTML/JSON-LD этого магазина — цикл
обхода разделов/товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

Пакетный источник (раздел, ВСЕГДА используется, живой запрос один на
страницу раздела): JSON-LD "OfferCatalog" (itemListElement c
name/url/price/image) — несёт name/url/price/photos/source_id ПАЧКОЙ на все
товары страницы разом. Явного бренда/артикула/характеристик в этом пакетном
источнике НЕТ.

Страница ТОВАРА (needs_product_visit) — владелец, 27.10.2026, по итогам 843
полученных страниц в соседнем прогоне (tools/catalog_enrich): "у 842 из 843
товаров Кувалды бренд со страницы и так стоит в названии" → бренд для
Кувалды НЕ требует визита вообще, берётся словарным поиском целым словом по
названию (gala_writer.find_brand_in_name(), импорт алгоритма из
tools/catalog_enrich/brand_dictionary.py — ПРАВИЛО №6, без своей второй
"угадайки"). needs_product_visit() == True ТОЛЬКО для той ~0.1% строк, где
словарь не нашёл известный бренд в названии — у них нет другого пакетного
способа получить бренд/артикул/характеристики, и только эти редкие строки
идут на страницу товара (JSON-LD "Product": brand {"@type":"Brand",
"name":"MAKITA"}, sku="DP4010" — явный артикул производителя, и пары
характеристик class="product-specs__characteristics-item"><span>Имя</span>
<span>Значение</span> — НЕ "Параметр N", как делал старый
harvest_kuvalda_massive_catalog.py, который вообще не заходил на товар и
угадывал бренд/артикул по первому/последнему слову названия)."""
from __future__ import annotations

import json
import re
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.http import HttpClient
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "kuvalda"
CATEGORY_INDEX_URL = "https://www.kuvalda.ru/catalog/"
BASE_URL = "https://www.kuvalda.ru"

# Статический список разделов для обхода (владелец может расширить/заменить
# discover_categories() динамическим списком — см. эту функцию ниже). Список
# короткий сознательно: полный обход каталога запускать не положено этим
# заданием, он требуется только для последующего реального прогона.
CATEGORIES: list[tuple[str, str, list[str]]] = [
    ("https://www.kuvalda.ru/catalog/1854/makita/", "Makita", ["Инструменты", "Makita"]),
]

_CAT_LINK_RE = re.compile(r'<a[^>]*href="(/catalog/\d+[^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_SPEC_ITEM_RE = re.compile(
    r'product-specs__characteristics-item">\s*<span>([^<]*)</span>\s*<span>([^<]*)</span>'
)
_JSONLD_RE = re.compile(r'<script\s+type="application/ld\+json"[^>]*>([\s\S]*?)</script>')


def discover_categories(client: HttpClient) -> list[tuple[str, str, list[str]]]:
    """Обходит /catalog/ и собирает реальные разделы (как в старом
    harvest_kuvalda_massive_catalog.py) — используется только явным вызовом
    при настоящем прогоне, не при импорте модуля и не в тестах."""
    html = client.fetch(CATEGORY_INDEX_URL)
    if not html:
        return []
    seen: dict[str, str] = {}
    for link, anchor in _CAT_LINK_RE.findall(html):
        title = _TAG_RE.sub(" ", anchor).strip()
        link_clean = link.strip().rstrip("/") + "/"
        if title and len(title) > 2 and not title.isdigit() and link_clean not in seen:
            seen[link_clean] = title
    return [(BASE_URL + path, title, ["Инструменты и оборудование", title]) for path, title in seen.items()]


def page_url(category_url: str, page: int) -> str:
    if page <= 1:
        return category_url
    return f"{category_url}page-{page}/"


def _find_jsonld(html: str, type_name: str) -> Optional[dict]:
    for block in _JSONLD_RE.findall(html):
        try:
            obj = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("@type") == type_name:
            return obj
    return None


def parse_category_page(html: str) -> list[dict]:
    catalog = _find_jsonld(html, "OfferCatalog")
    if not catalog:
        return []
    candidates = []
    for offer in catalog.get("itemListElement", []):
        url = offer.get("url")
        name = offer.get("name")
        if not url or not name:
            continue
        price = offer.get("price")
        image = offer.get("image")
        source_id_m = re.search(r"product-(\d+)", url)
        candidates.append({
            "name": name,
            "url": url,
            "price": float(price) if price else None,
            "photos": [image] if image and str(image).startswith("http") else [],
            "source_id": source_id_m.group(1) if source_id_m else None,
        })
    return candidates


def needs_product_visit(candidate: dict) -> bool:
    # Визит нужен ТОЛЬКО если словарь брендов не нашёл известный бренд в
    # названии (см. докстринг модуля — ~0.1% строк по данным владельца).
    name = candidate.get("name")
    return gala_writer.find_brand_in_name(name, set()) is None


def parse_product_page(html: str, url: str) -> dict:
    product = _find_jsonld(html, "Product") or {}
    characteristics = [
        {"name": name.strip(), "value": value.strip() or None, "unit": None, "in_description": False}
        for name, value in _SPEC_ITEM_RE.findall(html)
        if name.strip()
    ]
    return {
        "jsonld_brand": product.get("brand"),
        "manufacturer_article": (str(product.get("sku")).strip() if product.get("sku") else None),
        "characteristics": characteristics,
        "description": product.get("description"),
    }


def build_item(candidate: dict, enrichment: dict, known_brands: set) -> Optional[dict]:
    name = candidate.get("name")
    if not name:
        return None
    url = candidate.get("url")
    characteristics = enrichment.get("characteristics") or []

    if enrichment:
        # Эта строка попала на страницу товара (словарь не нашёл бренд в
        # названии, см. needs_product_visit) — артикул/характеристики
        # берём ИМЕННО со страницы, не выдумываем.
        manufacturer = gala_writer.resolve_manufacturer(
            name, enrichment.get("jsonld_brand"), characteristics, known_brands,
        )
        manufacturer_article = enrichment.get("manufacturer_article")
        description = enrichment.get("description")
    else:
        # Без визита: бренд — тем же словарным поиском, что принял решение
        # не заходить на страницу (needs_product_visit).
        manufacturer = gala_writer.find_brand_in_name(name, known_brands)
        manufacturer_article = None
        description = None

    return gala_writer.build_item(
        name=name,
        unit="шт",
        price=candidate.get("price"),
        currency="RUB" if candidate.get("price") is not None else None,
        manufacturer=manufacturer,
        manufacturer_article=manufacturer_article,
        store_article=candidate.get("source_id"),
        description=description,
        characteristics=characteristics,
        photos=candidate.get("photos"),
        links=[{"url": url, "price": candidate.get("price")}] if url else [],
        source_url=url,
        source_id=candidate.get("source_id"),
        seller_inn=gala_writer.seller_inn_for(url),
    )


SPEC = StoreSpec(
    name=STORE_NAME,
    categories=CATEGORIES,
    page_url=page_url,
    parse_category_page=parse_category_page,
    needs_product_visit=needs_product_visit,
    parse_product_page=parse_product_page,
    build_item=build_item,
    max_pages_per_category=3,
    # Старый harvest_kuvalda_massive_catalog.py был однопоточным (sleep
    # 0.8-1.5с между запросами, без ThreadPoolExecutor) — он НИКОГДА не
    # заходил на товар, поэтому concurrency здесь не для товарных визитов
    # имеет значение (их почти нет), а для той редкой ветки, где визит
    # всё же нужен.
    concurrency=1,
    default_pause_per_domain=1.0,
    category_has_price=True,
)


def harvest(
    out_path: str,
    limit_categories: Optional[int] = None,
    resume: bool = False,
    pause_per_domain: Optional[float] = None,
    previous_items: Optional[list] = None,
    prices_only: bool = False,
    with_details: bool = False,
) -> dict:
    return _run_harvest(
        SPEC, out_path, limit_categories=limit_categories, resume=resume,
        pause_per_domain=pause_per_domain, previous_items=previous_items, prices_only=prices_only,
        with_details=with_details,
    )
