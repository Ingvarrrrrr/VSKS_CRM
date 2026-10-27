"""Сборщик promalper.com. Только парсинг HTML/JSON-LD этого магазина —
цикл обхода разделов/товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

Проверено на живых фикстурах (tools/harvest/tests/fixtures/promalper_*.html,
27.10.2026, 3 живых запроса — 1 раздел + 2 товара):
  - Раздел — обычный HTML-каталог WooCommerce, ссылки `href="https://
    promalper.com/product/<slug>/"` (нужен визит на каждый товар — в
    разделе нет ни цены, ни характеристик).
  - Страница товара несёт JSON-LD `@type":"Product"` c `name`, `sku`
    (внутренний код WooCommerce магазина, например "0961"/"4651" — это
    store_article, НЕ артикул производителя), `offers[0].price`/
    `priceCurrency`.
  - Настоящие характеристики — WooCommerce product_attributes таблица
    `<th>Имя</th><td>Значение</td>` (Бренд/Страна бренда/Вес/Сертификат
    EAC/ГОСТ/Цвет на живых фикстурах) — это ЕДИНСТВЕННЫЙ источник бренда
    и страны, берём ИМЕННО отсюда:
      * "Бренд" → manufacturer (живые значения "Camp", "DPS" — настоящие
        бренды, не выдуманные);
      * "Страна бренда" → country_origin (единственное поле страны на
        странице; НЕ подставляем "Россия" по умолчанию, как делал старый
        harvest_promalper_height_safety.py, если поле не найдено).
    Текст `description` в JSON-LD тоже несёт те же данные в виде
    "Имя: значение" построчно (размеры/нагрузка) — здесь НЕ разбирается
    повторно, чтобы не дублировать характеристики из таблицы атрибутов
    (ПРАВИЛО №6, один источник на характеристику).
  - manufacturer_article: отдельного поля артикула производителя на живых
    фикстурах нет — остаётся None (брак старого сборщика: он пытался
    выдернуть "артикул" регулярным выражением по шаблону заглавных букв и
    цифр прямо из названия товара — это модель, не артикул)."""
from __future__ import annotations

import json
import re
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "promalper"
BASE_URL = "https://promalper.com"

# Статический короткий список разделов (владелец может расширить — полный
# список см. в старом harvest_promalper_height_safety.py). Полный обход
# каталога этим заданием не запускается.
CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "https://promalper.com/catalog/karabiny/",
        "Карабины и соединительные элементы",
        ["СИЗ от падения с высоты", "Карабины"],
    ),
]

_PRODUCT_LINK_RE = re.compile(r'href="(https://promalper\.com/product/[^"]+/)"')
_LDJSON_RE = re.compile(r'<script\s+type="application/ld\+json"[^>]*>([\s\S]*?)</script>')
_ATTR_ROW_RE = re.compile(r"<th[^>]*>([^<]+)</th>\s*<td[^>]*>([\s\S]*?)</td>")
_TAG_RE = re.compile(r"<[^>]+>")


def page_url(category_url: str, page: int) -> str:
    if page <= 1:
        return category_url
    return f"{category_url}page/{page}/"


def parse_category_page(html: str) -> list[dict]:
    seen = set()
    candidates = []
    for url in _PRODUCT_LINK_RE.findall(html):
        if url not in seen:
            seen.add(url)
            candidates.append({"name": None, "url": url})
    return candidates


def needs_product_visit(candidate: dict) -> bool:
    return True


def _find_jsonld_product(html: str) -> dict:
    for block in _LDJSON_RE.findall(html):
        try:
            obj = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        graph = obj.get("@graph", [obj]) if isinstance(obj, dict) else obj
        for node in graph if isinstance(graph, list) else [graph]:
            if isinstance(node, dict) and node.get("@type") == "Product":
                return node
    return {}


def parse_product_page(html: str, url: str) -> dict:
    product = _find_jsonld_product(html)
    name = product.get("name")

    offers = product.get("offers")
    price = None
    if isinstance(offers, list) and offers:
        price = offers[0].get("price")
    elif isinstance(offers, dict):
        price = offers.get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    characteristics = []
    brand = None
    country = None
    for raw_name, raw_value in _ATTR_ROW_RE.findall(html):
        name_clean = raw_name.strip()
        value_clean = _TAG_RE.sub(" ", raw_value).strip()
        if not name_clean or not value_clean:
            continue
        characteristics.append({"name": name_clean, "value": value_clean, "unit": None, "in_description": False})
        name_lower = name_clean.lower()
        if name_lower == "бренд":
            brand = value_clean
        elif name_lower == "страна бренда":
            country = value_clean

    image = product.get("image")

    return {
        "name": name,
        "price": price,
        "store_article": str(product.get("sku")).strip() if product.get("sku") else None,
        "jsonld_brand": brand,
        "characteristics": characteristics,
        "country_origin": country,
        "photos": [image] if isinstance(image, str) and image.startswith("http") else [],
    }


def build_item(candidate: dict, enrichment: dict, known_brands: set) -> Optional[dict]:
    name = enrichment.get("name")
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
        characteristics=characteristics,
        photos=enrichment.get("photos"),
        links=[{"url": url, "price": price}] if url else [],
        source_url=url,
        source_id=enrichment.get("store_article"),
        country_origin=enrichment.get("country_origin"),
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
    # Старый harvest_promalper_height_safety.py был однопоточным (sleep
    # 0.3с, без ThreadPoolExecutor) — нет пакетного API, needs_product_visit
    # остаётся True (визит неизбежен).
    concurrency=1,
    default_pause_per_domain=0.3,
    category_has_price=False,  # цена только на странице товара
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
