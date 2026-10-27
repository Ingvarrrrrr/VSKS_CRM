"""Сборщик magazin01.ru. Только парсинг HTML/JSON-LD этого магазина — цикл
обхода разделов/товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

⚠️ НУЖНА ДОРАБОТКА — фикстуры НЕ подтверждены живой страницей. Владелец
прямо запретил живые запросы к magazin01.ru в рамках этой задачи (на
магазин сейчас идёт отдельный прогон tools/catalog_enrich, и его нельзя
дополнительно нагружать), а в кэше дозаполнения HTML-страниц этого
магазина не нашлось (tools/catalog_enrich хранит только логи прогона, не
сами страницы). Разметка ниже воспроизведена по ДВУМ уже существующим
источникам, но tools/harvest/tests/fixtures/magazin01_*.html —
СИНТЕТИЧЕСКИЕ (не снятые живьём) файлы, сделанные по этой же разметке:
  1. tools/catalog_enrich/extractors.py (комментарий в начале файла,
     проверено на реальных страницах 27.10.2026 другим прогоном): JSON-LD
     `<script type="application/ld+json">` с `"@type":"Product"` несёт
     `brand.name` (пример из отчёта: "НПО Пульс") и `sku` — у magazin01
     это 13-значный ВНУТРЕННИЙ код магазина (контрольная цифра EAN не
     сходится — это не штрихкод), поэтому идёт в store_article, НЕ в
     manufacturer_article.
  2. Старый harvest_all_fire_now.py (не прошедший ревью по ПРАВИЛУ №6)
     читал характеристики из пар `<div class="properties__title">Имя</div>
     <span>:</span><div class="properties__value">Значение</div>` — класс
     использован ниже, но сама пара НЕ подтверждена этой задачей на живой
     странице (отсюда доработка: при следующем окне живых запросов к
     magazin01.ru — снять 1 реальную страницу товара и проверить, что
     properties__title/properties__value действительно так называются
     сейчас, прежде чем запускать настоящий сбор).
  - Раздел — sitemap `https://magazin01.ru/sitemap-iblock-<N>.xml` (список
    `<loc>` с `/product/` в пути — это сразу список товаров, карточка
    раздела у magazin01 не используется, см. старый harvest_all_fire_now.py).
    needs_product_visit() всегда True — весь разбор идёт со страницы
    товара, candidate из "раздела" содержит только url."""
from __future__ import annotations

import json
import re
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "magazin01"
BASE_URL = "https://magazin01.ru"

# sitemap-раздел используется как "категория" — сам URL раздела в терминах
# StoreSpec это адрес sitemap-файла, а не каталожной страницы (см.
# докстринг модуля). Владелец может расширить список sitemap-файлов по
# https://magazin01.ru/sitemap.xml (индекс всех sitemap-iblock-*.xml).
CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "https://magazin01.ru/sitemap-iblock-206.xml",
        "Пожарное оборудование",
        ["Пожарное оборудование и инвентарь"],
    ),
]

_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")
_LDJSON_RE = re.compile(r'application/ld\+json"[^>]*>([\s\S]*?)</script>')
_PROP_RE = re.compile(
    r'properties__title[^"]*"[^>]*>([^<]+)</div>\s*<span[^>]*>:</span>\s*'
    r'<div class="properties__value[^"]*"[^>]*>([^<]*)</div>'
)


def page_url(sitemap_url: str, page: int) -> str:
    # Sitemap не постраничный — весь список отдаётся одним файлом.
    return sitemap_url


def parse_category_page(xml_text: str) -> list[dict]:
    candidates = []
    for loc in _LOC_RE.findall(xml_text):
        if "/product/" in loc:
            candidates.append({"name": None, "url": loc.strip()})
    return candidates


def needs_product_visit(candidate: dict) -> bool:
    return True


def _find_jsonld_product(html: str) -> dict:
    for block in _LDJSON_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return {}


def parse_product_page(html: str, url: str) -> dict:
    product = _find_jsonld_product(html)
    name = product.get("name")
    if not name:
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
        name = re.sub(r"<[^>]+>", " ", h1.group(1)).strip() if h1 else None

    image = product.get("image")
    if isinstance(image, str):
        if image.startswith("//"):
            image = "https:" + image
        elif image.startswith("/"):
            image = BASE_URL + image

    offers = product.get("offers") or {}
    price = None
    if isinstance(offers, dict):
        price = offers.get("price")
    elif isinstance(offers, list) and offers:
        price = offers[0].get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    characteristics = []
    for raw_name, raw_value in _PROP_RE.findall(html):
        raw_name = re.sub(r"\?.*", "", raw_name).strip()
        raw_value = raw_value.strip()
        if raw_name and raw_value:
            characteristics.append({"name": raw_name, "value": raw_value, "unit": None, "in_description": False})

    brand = (product.get("brand") or {}).get("name") if isinstance(product.get("brand"), dict) else product.get("brand")

    return {
        "name": name,
        "description": product.get("description"),
        "photos": [image] if image else [],
        "price": price,
        "store_article": str(product.get("sku")).strip() if product.get("sku") else None,
        "jsonld_brand": brand,
        "characteristics": characteristics,
    }


def build_item(candidate: dict, enrichment: dict, known_brands: set) -> Optional[dict]:
    name = enrichment.get("name") or candidate.get("name")
    if not name:
        return None
    url = candidate.get("url")
    characteristics = enrichment.get("characteristics") or []

    manufacturer = gala_writer.resolve_manufacturer(
        name, enrichment.get("jsonld_brand"), characteristics, known_brands,
    )

    price = enrichment.get("price")
    return gala_writer.build_item(
        name=name,
        unit="шт",
        price=price,
        currency="RUB" if price is not None else None,
        manufacturer=manufacturer,
        manufacturer_article=None,
        store_article=enrichment.get("store_article"),
        description=enrichment.get("description"),
        characteristics=characteristics,
        photos=enrichment.get("photos"),
        links=[{"url": url, "price": price}] if url else [],
        source_url=url,
        source_id=enrichment.get("store_article"),
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
    max_pages_per_category=1,
)


def harvest(out_path: str, limit_categories: Optional[int] = None, resume: bool = False, pause_per_domain: float = 1.0) -> dict:
    return _run_harvest(SPEC, out_path, limit_categories=limit_categories, resume=resume, pause_per_domain=pause_per_domain)
