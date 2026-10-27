"""Сборщик regard.ru. Только парсинг HTML/JSON-LD этого магазина — цикл
обхода разделов/товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

Проверено на живых фикстурах (tools/harvest/tests/fixtures/regard_*.html,
27.10.2026):
  - Страница РАЗДЕЛА отдаёт JSON-LD "OfferCatalog" — БЕЗ бренда/
    характеристик.
  - Владелец, 27.10.2026: по умолчанию (как старый harvest_regard_massive.py)
    товар НЕ открывается — needs_product_visit() == False всегда. Бренд
    берётся словарём по названию (gala_writer.find_brand_in_name),
    manufacturer_article — тот же FALLBACK (код в скобках на конце
    названия, см. _manufacturer_article_from), характеристики пустые.
    Визит на товар включается флагом CLI --with-details
    (StoreSpec.supports_details=True) — тогда используется JSON-LD
    "Product" с brand ({"@type":"Brand","name":"Netac"}), sku (числовой ID
    товара В МАГАЗИНЕ, совпадает с ID в URL — это store_article, НЕ
    артикул производителя) и mpn (часто null).
  - С --with-details в HTML страницы товара — настоящие пары характеристик
    вида <div class="CharacteristicsItem_name__<хеш>"><span>Имя</span>...
    <div class="CharacteristicsItem_value__<хеш>">Значение</div> (хеш CSS
    modules — сравниваем по префиксу класса, не по точному значению).
    Характеристика "Код производителя" — артикул ПРОИЗВОДИТЕЛЯ (пример:
    NTSHD4P32DP-16K), основной источник manufacturer_article при визите
    (брак старого harvest_regard_massive.py: он резал description по
    запятым в "Параметр N" и никогда не заходил на страницу товара)."""
from __future__ import annotations

import json
import re
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.http import HttpClient
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "regard"

# Статический короткий список разделов (владелец может расширить). Полный
# обход каталога этим заданием не запускается.
CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "https://www.regard.ru/catalog/1010/operativnaya-pamyat",
        "Оперативная память",
        ["Оргтехника и ИТ", "Комплектующие", "ОЗУ"],
    ),
]

_JSONLD_RE = re.compile(r'<script\s+type="application/ld\+json">([\s\S]*?)</script>')
_SPEC_ITEM_RE = re.compile(
    r'CharacteristicsItem_name__[\w]+"><span>([^<]*)</span>.*?'
    r'CharacteristicsItem_value__[\w]+">(.*?)</div></div>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_TRAILING_CODE_RE = re.compile(r"\(([^()]{4,})\)\s*$")
_JUNK_NAME_PREFIXES = ("технические характеристики",)
_JUNK_VALUE_PREFIXES = ("скачать",)


def page_url(category_url: str, page: int) -> str:
    return f"{category_url}?page={page}"


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
        candidates.append({
            "name": name,
            "url": url,
            "price": float(price) if price else None,
            "photos": [image] if image and str(image).startswith("http") else [],
        })
    return candidates


def needs_product_visit(candidate: dict) -> bool:
    # Владелец, 27.10.2026: по умолчанию НЕ открывать товар (как старый
    # harvest_regard_massive.py) — бренд из названия по словарю
    # (gala_writer.find_brand_in_name), артикул — код в скобках в конце
    # названия (см. build_item), характеристики пустые. Визит включается
    # только флагом CLI --with-details (StoreSpec.supports_details=True).
    return False


def _parse_characteristics(html: str) -> list[dict]:
    characteristics = []
    for name, value_html in _SPEC_ITEM_RE.findall(html):
        name = name.strip()
        value = _TAG_RE.sub("", value_html).replace("&nbsp", " ").strip()
        if not name or not value:
            continue
        if name.strip().lower().startswith(_JUNK_NAME_PREFIXES):
            continue
        if value.strip().lower().startswith(_JUNK_VALUE_PREFIXES):
            continue
        characteristics.append({"name": name, "value": value, "unit": None, "in_description": False})
    return characteristics


def _manufacturer_article_from(name: str, product_jsonld: dict, characteristics: list[dict]) -> Optional[str]:
    for c in characteristics:
        if c["name"].strip().lower() == "код производителя":
            return c["value"] or None

    mpn = product_jsonld.get("mpn")
    if mpn:
        return str(mpn).strip() or None

    # FALLBACK (владелец, см. docstring модуля): код в скобках на конце
    # названия товара, только если нет явного поля.
    m = _TRAILING_CODE_RE.search(name or "")
    if m and any(ch.isdigit() for ch in m.group(1)):
        return m.group(1).strip()
    return None


def parse_product_page(html: str, url: str) -> dict:
    product = _find_jsonld(html, "Product") or {}
    characteristics = _parse_characteristics(html)
    name = product.get("name") or ""
    return {
        "jsonld_brand": product.get("brand"),
        "manufacturer_article": _manufacturer_article_from(name, product, characteristics),
        "store_sku": str(product.get("sku")).strip() if product.get("sku") else None,
        "characteristics": characteristics,
    }


def build_item(candidate: dict, enrichment: dict, known_brands: set) -> Optional[dict]:
    name = candidate.get("name")
    if not name:
        return None
    url = candidate.get("url")

    if enrichment:
        # --with-details — товар реально открыт, данные со страницы.
        characteristics = enrichment.get("characteristics") or []
        manufacturer = gala_writer.resolve_manufacturer(
            name, enrichment.get("jsonld_brand"), characteristics, known_brands,
        )
        manufacturer_article = enrichment.get("manufacturer_article")
    else:
        # Без визита (по умолчанию) — бренд словарём по названию,
        # характеристики пустые (раздел их не несёт), артикул — та же
        # фолбэк-эвристика (код в скобках на конце названия), что и при
        # визите, см. _manufacturer_article_from.
        characteristics = []
        manufacturer = gala_writer.find_brand_in_name(name, known_brands)
        manufacturer_article = _manufacturer_article_from(name, {}, [])

    store_article = enrichment.get("store_sku")
    source_id_m = re.search(r"/product/(\d+)", url) if url else None
    if not store_article and source_id_m:
        store_article = source_id_m.group(1)

    return gala_writer.build_item(
        name=name,
        unit="шт",
        price=candidate.get("price"),
        currency="RUB" if candidate.get("price") is not None else None,
        manufacturer=manufacturer,
        manufacturer_article=manufacturer_article,
        store_article=store_article,
        characteristics=characteristics,
        photos=candidate.get("photos"),
        links=[{"url": url, "price": candidate.get("price")}] if url else [],
        source_url=url,
        source_id=source_id_m.group(1) if source_id_m else None,
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
    # Старый harvest_regard_massive.py был однопоточным (sleep 1.2-3с между
    # запросами, без ThreadPoolExecutor) и НИКОГДА не заходил на товар —
    # никакого бренда/API карточки пачкой у regard не найдено ни в живых
    # фикстурах, ни в старых скриптах probe_regard_api.py/find_regard_api.py
    # (пробные REST-эндпойнты не подтверждены). needs_product_visit теперь
    # False по умолчанию (как у старого сборщика) — визит включается
    # только флагом --with-details (владелец, 27.10.2026).
    concurrency=1,
    default_pause_per_domain=1.2,
    category_has_price=True,
    supports_details=True,
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
