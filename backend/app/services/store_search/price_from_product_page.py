"""Довизит на страницу товара ЗА ЦЕНОЙ, когда страница поиска/листинга её не
отдаёт (magazin01.ru, возможно promalper.com при будущих изменениях вёрстки).
Разбор — schema.org Product/Offer (JSON-LD `@type":"Product"` →
`offers.price`, тот же паттерн, что уже проверен живыми фикстурами в
tools/harvest/stores/magazin01.py) + запасной путь `itemprop="price"`
(meta/content или текст) — ОБА пути уже встречались в харвест-сборщиках
разных магазинов (ПРАВИЛО №6 — переиспользуем те же эвристики, не второй
набор регулярок на каждый магазин).

30.10.2026: часть харвест-парсеров перенесена в
backend/app/services/store_pages/ (ПРАВИЛО №6) — take.py для них вызывает
ИМЕННО эти store_pages-модули, не этот общий JSON-LD-разбор. Этот модуль
остаётся ЕДИНСТВЕННЫМ источником разбора страницы товара ТОЛЬКО для
магазинов, у которых нет (и по плану не будет — см. докстринг
store_pages/__init__.py) отдельного store_pages-модуля: avtoall/chipdip/emex
(их tools/harvest/stores/<магазин>.py изменены параллельной сессией и не
переносились) — отсюда и additionalProperty→characteristics ниже, нужное
именно для этих трёх магазинов.

ДОРАБОТКА (QA живого поиска 30.10.2026, «Взять» из chipdip): chipdip.ru НЕ
несёт сам узел Product внутри JSON-LD (его единственный `<script
type="application/ld+json">` на странице товара — BreadcrumbList, не
Product) — description/brand/sku оставались пустыми ВСЕГДА для этого
магазина, хотя они ЕСТЬ на странице как schema.org microdata (`itemprop=`
на обычных тегах, не JSON-LD) — добавлены те же три поля через itemprop-
регулярку (ТОТ ЖЕ приём, что уже есть у price/image ниже, просто для трёх
новых полей, Правило №6 — не второй механизм, тот же запасной путь).
Характеристики chipdip — отдельная проприетарная таблица
`<table id="productparams">` (НЕ schema.org additionalProperty) —
_characteristics_from_params_table ниже, используется ТОЛЬКО если JSON-LD
additionalProperty ничего не дал (avtoall/emex эту таблицу, скорее всего,
не несут вовсе — тогда regex просто не совпадёт, доп. путь не навредит)."""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from html import unescape as _html_unescape
from typing import Optional

_LDJSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>([\s\S]*?)</script>', re.IGNORECASE)
_ITEMPROP_PRICE_META_RE = re.compile(r'itemprop="price"[^>]*content="([^"]+)"', re.IGNORECASE)
_ITEMPROP_PRICE_TEXT_RE = re.compile(r'itemprop="price"[^>]*>([^<]+)<', re.IGNORECASE)
_ITEMPROP_IMAGE_RE = re.compile(r'itemprop="image"[^>]*(?:content|src)="([^"]+)"', re.IGNORECASE)

# Запасной путь для description/brand/sku — та же идея, что у price/image
# выше, для страниц, где Product размечен microdata (itemprop= на обычных
# тегах), а не JSON-LD (chipdip.ru, см. докстринг модуля).
_ITEMPROP_DESCRIPTION_RE = re.compile(
    r'itemprop="description"[^>]*>([\s\S]*?)\n\s*</div>', re.IGNORECASE,
)
_ITEMPROP_BRAND_META_RE = re.compile(r'itemprop="brand"[^>]*content="([^"]+)"', re.IGNORECASE)
_ITEMPROP_BRAND_TEXT_RE = re.compile(r'itemprop="brand"[^>]*>([^<]+)<', re.IGNORECASE)
_ITEMPROP_SKU_RE = re.compile(r'itemprop="sku"[^>]*>([^<]+)<', re.IGNORECASE)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")

# Таблица характеристик chipdip.ru (проприетарная вёрстка, НЕ schema.org) —
# <table id="productparams">, строки <td class="product__param-name">ИМЯ</td>
# <td class="product__param-value">ЗНАЧЕНИЕ</td> (см. докстринг модуля).
_PARAM_TABLE_RE = re.compile(
    r'id="productparams"[^>]*>([\s\S]*?)</table>', re.IGNORECASE,
)
_PARAM_ROW_RE = re.compile(
    r'<td[^>]*product__param-name[^>]*>(.*?)</td>\s*<td[^>]*product__param-value[^>]*>(.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_tags(raw: str) -> str:
    return _html_unescape(_STRIP_TAGS_RE.sub(" ", raw)).strip()


def _characteristics_from_params_table(html: str) -> list[dict]:
    table_m = _PARAM_TABLE_RE.search(html)
    if not table_m:
        return []
    characteristics = []
    for name_raw, value_raw in _PARAM_ROW_RE.findall(table_m.group(1)):
        name = _strip_tags(name_raw)
        value = _strip_tags(value_raw)
        if not name or not value:
            continue
        characteristics.append({"name": name, "value": value, "unit": None, "in_description": False})
    return characteristics


def _to_decimal(raw) -> Optional[Decimal]:
    if raw is None:
        return None
    text = re.sub(r"[^\d.,]", "", str(raw)).replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _find_jsonld_products(html: str) -> list[dict]:
    out = []
    for block in _LDJSON_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        graph = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in graph if isinstance(graph, list) else [graph]:
            if isinstance(node, dict) and node.get("@type") == "Product":
                out.append(node)
    return out


def extract_price_and_image(html: str) -> tuple[Optional[Decimal], Optional[str]]:
    """html страницы ТОВАРА → (цена, image_url) — None/None, если страница
    не отдала ни JSON-LD Product, ни itemprop="price" (чужой/неожиданный
    шаблон страницы; вызывающий адаптер в этом случае просто не добавляет
    цену к предложению, не выдумывает её)."""
    if not html:
        return None, None

    for product in _find_jsonld_products(html):
        offers = product.get("offers")
        price = None
        if isinstance(offers, dict):
            price = offers.get("price")
        elif isinstance(offers, list) and offers:
            price = offers[0].get("price")
        price_dec = _to_decimal(price)
        image = product.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if price_dec is not None:
            return price_dec, image if isinstance(image, str) else None

    m = _ITEMPROP_PRICE_META_RE.search(html) or _ITEMPROP_PRICE_TEXT_RE.search(html)
    price_dec = _to_decimal(m.group(1)) if m else None
    img_m = _ITEMPROP_IMAGE_RE.search(html)
    image = img_m.group(1) if img_m else None
    return price_dec, image


def _characteristics_from_jsonld_product(product: dict) -> list[dict]:
    """additionalProperty[] schema.org ({"@type":"PropertyValue","name",
    "value",["unitText"]}) → та же форма характеристик
    [{"name","value","unit","in_description"}], что собирают сборщики
    tools/harvest/* и backend/app/services/store_pages/* (ПРАВИЛО №6 — один
    формат характеристик на весь проект, build_tech_description/item_tz его
    и ждут). Для магазинов, у которых НЕТ отдельного store_pages-модуля
    (avtoall/chipdip/emex, см. докстринг backend/app/services/store_pages/
    __init__.py) — это единственный путь получить характеристики со
    страницы товара при довизите в take.py."""
    raw = product.get("additionalProperty")
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    characteristics = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not name.strip():
            continue
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        unit = item.get("unitText")
        characteristics.append({
            "name": _html_unescape(name.strip()),
            "value": _html_unescape(str(value).strip()),
            "unit": _html_unescape(str(unit).strip()) if isinstance(unit, str) and unit.strip() else None,
            "in_description": False,
        })
    return characteristics


def extract_product_details(html: str) -> dict:
    """html страницы товара → {"price", "image_url", "description", "article",
    "manufacturer", "characteristics"} — довизит этапа 2 «Взять» (POST
    /api/products/store-take, app/services/store_search/take.py, владелец
    29.10.2026). ТА ЖЕ эвристика JSON-LD Product / itemprop="price", что
    extract_price_and_image() выше (ПРАВИЛО №6 — второй разбор страницы не
    пишем, этот метод читает больше полей из того же узла @type=Product):
    sku/mpn → артикул, brand.name/brand → производитель, description — как
    есть, additionalProperty[] → characteristics (см.
    _characteristics_from_jsonld_product).

    Отсутствующее поле — None/[]; вызывающий код (take.py) не затирает то,
    что уже было известно из предложения поиска (offer.name/offer.price/...).

    description/article/manufacturer декодируются html.unescape ЗДЕСЬ, одним
    местом для этого источника (ПРАВИЛО №6, тот же дефект сущностей в имени
    товара, что у StoreOffer в base.py, см. его docstring — на всякий
    случай, если сайт магазина кладёт в JSON-LD уже HTML-экранированный
    текст, как это встретилось в карточках поиска chipdip.ru)."""
    out: dict = {
        "price": None, "image_url": None, "description": None,
        "article": None, "manufacturer": None, "characteristics": [],
    }
    if not html:
        return out

    for product in _find_jsonld_products(html):
        if out["price"] is None:
            offers = product.get("offers")
            price = None
            if isinstance(offers, dict):
                price = offers.get("price")
            elif isinstance(offers, list) and offers:
                price = offers[0].get("price")
            out["price"] = _to_decimal(price)

        if out["image_url"] is None:
            image = product.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, str):
                out["image_url"] = image

        if out["description"] is None:
            desc = product.get("description")
            if isinstance(desc, str) and desc.strip():
                out["description"] = _html_unescape(desc.strip())

        if out["article"] is None:
            sku = product.get("sku") or product.get("mpn")
            if isinstance(sku, str) and sku.strip():
                out["article"] = _html_unescape(sku.strip())

        if out["manufacturer"] is None:
            brand = product.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")
            if isinstance(brand, str) and brand.strip():
                out["manufacturer"] = _html_unescape(brand.strip())

        if not out["characteristics"]:
            out["characteristics"] = _characteristics_from_jsonld_product(product)

    if out["price"] is None:
        m = _ITEMPROP_PRICE_META_RE.search(html) or _ITEMPROP_PRICE_TEXT_RE.search(html)
        if m:
            out["price"] = _to_decimal(m.group(1))
    if out["image_url"] is None:
        img_m = _ITEMPROP_IMAGE_RE.search(html)
        if img_m:
            out["image_url"] = img_m.group(1)

    # Запасной путь microdata (itemprop= на обычных тегах, не JSON-LD) —
    # chipdip.ru несёт description/brand/sku ТОЛЬКО так (см. докстринг
    # модуля, находка QA 30.10.2026): без этого шага три поля оставались
    # пустыми для магазина без своего store_pages-модуля.
    if out["description"] is None:
        m = _ITEMPROP_DESCRIPTION_RE.search(html)
        if m:
            text = _strip_tags(m.group(1))
            if text:
                out["description"] = text
    if out["manufacturer"] is None:
        m = _ITEMPROP_BRAND_META_RE.search(html) or _ITEMPROP_BRAND_TEXT_RE.search(html)
        if m:
            brand = _html_unescape(m.group(1).strip())
            if brand:
                out["manufacturer"] = brand
    if out["article"] is None:
        m = _ITEMPROP_SKU_RE.search(html)
        if m:
            sku = _html_unescape(m.group(1).strip())
            if sku:
                out["article"] = sku
    if not out["characteristics"]:
        out["characteristics"] = _characteristics_from_params_table(html)

    return out
