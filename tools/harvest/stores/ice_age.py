"""Сборщик ice-age.ru (АльпИндустрия / Ледниковый период, товарная группа
promalp). Только парсинг JSON-API этого магазина — цикл обхода разделов/
товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

Проверено на живых фикстурах (tools/harvest/tests/fixtures/ice_age_*.json,
27.10.2026, 3 живых запроса — 1 sitemap + 2 товара):
  - Платформа — InSales (НЕ Shopify, как предполагал старый
    harvest_all_promalp_now.py по комментарию "Shopify-like" — URL
    `<product_url>.json` совпадает по форме, но поля InSales-специфичные:
    `variant_field_values`, `quantity_at_warehouse0`, images с
    `cdn.insales-shop.ru`).
  - Раздел — sitemap.xml целиком (список `<loc>` с `/product/` в пути,
    без пагинации по разделам) — как и у magazin01/medtehno, карточка
    каталога здесь не используется, нужен визит на каждый товар.
  - На странице товара ИМЕН характеристик НЕТ напрямую в списке
    `characteristics[]` — там только {`property_id`, `title`=ЗНАЧЕНИЕ}.
    Имя характеристики — в ОТДЕЛЬНОМ списке `properties[]` ({`id`,
    `title`=ИМЯ, `is_hidden`}), сопоставляется по `property_id`. Пары с
    `is_hidden=true` (на фикстурах это служебное поле "Статус"="Архивный
    товар") ИСКЛЮЧАЮТСЯ — это не характеристика товара, а внутренний
    технический флаг сайта, выдавать его за ТЗ было бы браком (старый
    harvest_all_promalp_now.py вообще не различал properties/
    characteristics и использовал необъяснённые ключи 'title'/'name' —
    этот код их не находил и просто ничего не собирал).
  - Бренд — характеристика с property.permalink == "brend" (title
    "Бренд" на обеих живых фикстурах, значение "CAMP") — из неё, НЕ из
    первого слова названия.
  - `variants[0].sku` — артикул САМОГО ice-age (store_article), не
    производителя — отдельного поля "Артикул производителя" на живых
    фикстурах не найдено (ищем характеристику с "артикул" в названии как
    запасной источник на случай, если он появится у других товаров;
    пока такой нет — manufacturer_article остаётся None)."""
from __future__ import annotations

import json
import re
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "ice_age"

CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "https://ice-age.ru/sitemap.xml",
        "Снаряжение для альпинизма и промальпа",
        ["Снаряжение для высотных работ", "Альпинизм и промальп"],
    ),
]

_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")


def page_url(sitemap_url: str, page: int) -> str:
    return sitemap_url


def parse_category_page(xml_text: str) -> list[dict]:
    candidates = []
    for loc in _LOC_RE.findall(xml_text):
        loc = loc.strip()
        if "/product/" in loc:
            # candidate["url"] — то, что реально фетчит runner (JSON-API
            # этого товара), candidate["product_url"] — человекочитаемая
            # ссылка для покупателя (идёт в links/source_url у build_item).
            candidates.append({
                "name": None,
                "url": loc.rstrip("/") + ".json",
                "product_url": loc,
            })
    return candidates


def needs_product_visit(candidate: dict) -> bool:
    return True


def parse_product_page(raw: str, url: str) -> dict:
    # runner фетчит candidate["url"] (уже с суффиксом .json, см.
    # parse_category_page) — страница товара сама по себе ЕСТЬ JSON
    # `{"product": {...}}` платформы InSales.
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    product = data.get("product") or {}

    properties_by_id = {p["id"]: p for p in product.get("properties") or []}
    characteristics = []
    brand = None
    manufacturer_article = None
    for ch in product.get("characteristics") or []:
        prop = properties_by_id.get(ch.get("property_id"))
        if not prop or prop.get("is_hidden"):
            continue
        name = (prop.get("title") or "").strip()
        value = (ch.get("title") or "").strip()
        if not name or not value:
            continue
        characteristics.append({"name": name, "value": value, "unit": None, "in_description": False})
        if prop.get("permalink") == "brend":
            brand = value
        elif "артикул" in name.lower():
            manufacturer_article = value

    variants = product.get("variants") or []
    price = None
    store_article = None
    if variants:
        try:
            price = float(variants[0].get("price"))
        except (TypeError, ValueError):
            price = None
        store_article = variants[0].get("sku")

    images = [img.get("original_url") for img in product.get("images") or [] if img.get("original_url")]

    return {
        "name": (product.get("title") or "").strip() or None,
        "price": price,
        "store_article": store_article,
        "manufacturer_article": manufacturer_article,
        "jsonld_brand": brand,
        "characteristics": characteristics,
        "photos": images[:3],
    }


def build_item(candidate: dict, enrichment: dict, known_brands: set) -> Optional[dict]:
    name = enrichment.get("name")
    if not name:
        return None
    url = candidate.get("product_url") or candidate.get("url")
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
        manufacturer_article=enrichment.get("manufacturer_article"),
        store_article=enrichment.get("store_article"),
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
    # Старый harvest_all_promalp_now.py: ThreadPoolExecutor max_workers=30
    # (JSON InSales per-товар, уже используется как "визит" ниже — нет
    # отдельного batch-API по многим id сразу).
    concurrency=30,
    default_pause_per_domain=0.2,
    category_has_price=False,  # цена только в JSON товара, не в sitemap
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
