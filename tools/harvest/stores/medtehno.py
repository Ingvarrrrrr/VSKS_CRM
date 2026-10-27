"""Сборщик medtehno.ru. Только парсинг HTML этого магазина — цикл обхода
разделов/товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

Проверено на живых фикстурах (tools/harvest/tests/fixtures/medtehno_*.html,
27.10.2026, 3 живых запроса — 1 раздел + 2 товара; sitemap-iblock-37.xml из
старого harvest_all_medtehno_now.py на практике оказался устаревшим кэшем
(оба первых URL из него отдают 404) — раздел для фикстур взят живым
обходом каталога, а не из sitemap):
  - НЕТ JSON-LD @type=Product (старый harvest_all_medtehno_now.py на это
    рассчитывал — на живых фикстурах такого блока не нашлось вообще).
    Данные — microdata `itemprop=`: `<span itemprop="price">10990</span>`
    (без валюты внутри — рубли, см. соседний `itemprop="priceCurrency"`)
    и `<meta itemprop="image" content="...">`.
  - Настоящие характеристики — HTML-таблица `<tr><td>Имя</td><td>
    Значение</td></tr>` (22 пары на живой фикстуре 1: вес/габариты/тип
    рамы/нагрузка и т.д.) — используется НАПРЯМУЮ, значения местами несут
    `&nbsp;`/переносы строк (особенно у товаров с таблицей размеров —
    фикстура 2), чистим пробелы и `&nbsp;`, но саму пару не выбрасываем и
    не укорачиваем до "Параметр N" (брак старого сборщика, который гадал
    по `<div class="prop">` — такого класса на живых страницах не нашлось).
  - Явного поля бренда/артикула производителя на живых фикстурах НЕТ —
    manufacturer определяется только через gala_writer.resolve_manufacturer
    (JSON-LD нет, значит только по характеристике "Производитель"/
    известным токенам в названии, если они есть) — НЕ "Производитель"
    по умолчанию, НЕ код из URL-слага (брак старого сборщика пропускал
    артикул вообще, что честно, но пусть остаётся честным и у нас:
    manufacturer_article всегда None, store_article — слаг из URL)."""
from __future__ import annotations

import html as _html
import re
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "medtehno"
BASE_URL = "https://www.medtehno.ru"

# Статический короткий список разделов (владелец может расширить по
# /catalog/ на главной). Полный обход каталога этим заданием не запускается.
CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "https://www.medtehno.ru/catalog/invalid_kol/",
        "Инвалидные коляски",
        ["Медицинское и реабилитационное оборудование", "Инвалидные коляски"],
    ),
]

_PRODUCT_LINK_RE = re.compile(r'href="(/catalog/invalid_kol/[a-zA-Z0-9_\-]+/)"')
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL)
_PRICE_RE = re.compile(r'itemprop="price"[^>]*>([\d.]+)</span>')
_IMAGE_RE = re.compile(r'itemprop="image"[^>]*content="([^"]+)"')
_SPEC_ROW_RE = re.compile(
    r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>", re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    text = _TAG_RE.sub(" ", text)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def page_url(category_url: str, page: int) -> str:
    if page <= 1:
        return category_url
    return f"{category_url}?PAGEN_1={page}"


def parse_category_page(html: str) -> list[dict]:
    seen = set()
    candidates = []
    for rel in _PRODUCT_LINK_RE.findall(html):
        if "brand-" in rel or rel in seen:
            continue
        seen.add(rel)
        candidates.append({"name": None, "url": BASE_URL + rel})
    return candidates


def needs_product_visit(candidate: dict) -> bool:
    # Цена, характеристики и имя полностью отсутствуют в карточке
    # раздела у этого шаблона — визит всегда обязателен.
    return True


def parse_product_page(html: str, url: str) -> dict:
    h1 = _H1_RE.search(html)
    name = _clean(h1.group(1)) if h1 else None

    price_m = _PRICE_RE.search(html)
    price = float(price_m.group(1)) if price_m else None

    image_m = _IMAGE_RE.search(html)
    image = image_m.group(1) if image_m else None

    characteristics = []
    for raw_name, raw_value in _SPEC_ROW_RE.findall(html):
        name_clean = _clean(raw_name).rstrip(":").strip()
        value_clean = _clean(raw_value).strip()
        if name_clean and value_clean and len(name_clean) < 80:
            characteristics.append({"name": name_clean, "value": value_clean, "unit": None, "in_description": False})

    return {
        "name": name,
        "price": price,
        "photos": [image] if image else [],
        "characteristics": characteristics,
    }


def build_item(candidate: dict, enrichment: dict, known_brands: set) -> Optional[dict]:
    name = enrichment.get("name") or candidate.get("name")
    if not name:
        return None
    url = candidate.get("url")
    characteristics = enrichment.get("characteristics") or []

    manufacturer = gala_writer.resolve_manufacturer(
        name, None, characteristics, known_brands,
    )

    price = enrichment.get("price")
    slug = url.rstrip("/").split("/")[-1] if url else None
    return gala_writer.build_item(
        name=name,
        unit="шт",
        price=price,
        currency="RUB" if price is not None else None,
        manufacturer=manufacturer,
        manufacturer_article=None,
        store_article=slug,
        characteristics=characteristics,
        photos=enrichment.get("photos"),
        links=[{"url": url, "price": price}] if url else [],
        source_url=url,
        source_id=slug,
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
