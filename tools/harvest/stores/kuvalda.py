"""Сборщик kuvalda.ru. Только парсинг HTML/JSON-LD этого магазина — цикл
обхода разделов/товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

Проверено на живых фикстурах (tools/harvest/tests/fixtures/kuvalda_*.html,
27.10.2026):
  - Страница РАЗДЕЛА отдаёт JSON-LD "OfferCatalog" (itemListElement c
    name/url/price/image) — БЕЗ бренда и характеристик, поэтому
    needs_product_visit() для kuvalda всегда True.
  - Страница ТОВАРА отдаёт JSON-LD "Product" с полями brand
    ({"@type":"Brand","name":"MAKITA"}) и sku ("DP4010" — явный артикул
    производителя, печатается в конце названия товара) — брать ИМЕННО
    отсюда, не угадывать по первому слову названия (брак старого
    harvest_kuvalda_massive_catalog.py).
  - На странице товара есть настоящие пары характеристик
    class="product-specs__characteristics-item"><span>Имя</span>
    <span>Значение</span> — используются как characteristics, НЕ как
    "Параметр N" (второй брак старого сборщика)."""
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
    # Раздел kuvalda никогда не несёт бренд/характеристики — визит на
    # страницу товара обязателен всегда.
    return True


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

    manufacturer = gala_writer.resolve_manufacturer(
        name, enrichment.get("jsonld_brand"), characteristics, known_brands,
    )

    return gala_writer.build_item(
        name=name,
        unit="шт",
        price=candidate.get("price"),
        currency="RUB" if candidate.get("price") is not None else None,
        manufacturer=manufacturer,
        manufacturer_article=enrichment.get("manufacturer_article"),
        store_article=candidate.get("source_id"),
        description=enrichment.get("description"),
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
)


def harvest(out_path: str, limit_categories: Optional[int] = None, resume: bool = False, pause_per_domain: float = 1.0) -> dict:
    return _run_harvest(SPEC, out_path, limit_categories=limit_categories, resume=resume, pause_per_domain=pause_per_domain)
