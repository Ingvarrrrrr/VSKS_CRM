"""Разбор страницы товара ice-age.ru (платформа InSales, JSON-API) —
перенесено из tools/harvest/stores/ice_age.py (ПРАВИЛО №6, единственный
источник этой логики). Страница товара САМА ЕСТЬ JSON `{"product": {...}}`,
не HTML — вызывающий код (харвест/take.py) фетчит `<product_url>.json`.

characteristics[] несёт только {property_id, title=ЗНАЧЕНИЕ}; имя — в
отдельном properties[] ({id, title=ИМЯ, is_hidden}), сопоставляется по
property_id. Пары is_hidden=true исключаются. Бренд —
property.permalink == "brend"."""
from __future__ import annotations

import json


def product_page_fetch_url(url: str) -> str:
    """URL, который реально нужно СКАЧАТЬ для этого товара — страница
    товара ice-age.ru сама по себе HTML, а разбирать нужно JSON API
    платформы InSales по тому же адресу + ".json" (та же конвенция, что
    tools/harvest/stores/ice_age.py::parse_category_page строит для
    candidate["url"], см. его докстринг). take.py вызывает эту функцию
    ПЕРЕД HTTP-запросом, если она определена в store_pages-модуле магазина
    (по умолчанию — тот же `url`, без изменений)."""
    return url.rstrip("/") + ".json"


def parse_product_page(raw: str, url: str) -> dict:
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
