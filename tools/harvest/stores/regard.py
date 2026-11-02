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

import re
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.http import HttpClient
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest
from tools.harvest.stores._backend_bridge import load_store_page_module

STORE_NAME = "regard"

# Разбор страницы товара (JSON-LD "Product" + CharacteristicsItem_*) —
# backend/app/services/store_pages/regard.py (ПРАВИЛО №6, тот же код нужен
# live-поиску, take.py). find_jsonld переиспользуется ниже и для разбора
# страницы РАЗДЕЛА (OfferCatalog); manufacturer_article_from — ТАКЖЕ из
# build_item ниже, когда товар не посещался (фолбэк по коду в скобках).
_store_page = load_store_page_module("regard")
_find_jsonld = _store_page.find_jsonld
_manufacturer_article_from = _store_page.manufacturer_article_from
parse_product_page = _store_page.parse_product_page

# Статический короткий список разделов (владелец может расширить). Полный
# обход каталога этим заданием не запускается.
CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "https://www.regard.ru/catalog/1010/operativnaya-pamyat",
        "Оперативная память",
        ["Оргтехника и ИТ", "Комплектующие", "ОЗУ"],
    ),
]

def page_url(category_url: str, page: int) -> str:
    return f"{category_url}?page={page}"


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
