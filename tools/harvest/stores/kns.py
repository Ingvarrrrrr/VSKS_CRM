"""Сборщик kns.ru. Только парсинг HTML этого магазина — цикл обхода
разделов/товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

Проверено на живых фикстурах (tools/harvest/tests/fixtures/kns_*.html,
27.10.2026, 3 живых запроса — 1 раздел + характеристики 2 товаров):
  - Страница РАЗДЕЛА несёт настоящий GA4 datalayer `window.goodsList.push(
    {item_id, item_name, price, item_brand, item_variant, ...})` — это
    РЕАЛЬНЫЕ данные магазина (не выдумка): `item_brand` — бренд
    ("Huawei"), `item_variant` — артикул/PN производителя ("53014MTK",
    совпадает с характеристикой "PN" на отдельной странице товара —
    проверено на живой фикстуре). Брать бренд/артикул ИМЕННО отсюда —
    никогда не подставлять "Производитель"/strip-эвристику по бренду
    (брак старого harvest_kns_massive.py, который при отсутствии
    item_brand писал "Производитель" как бренд и рубил description по
    запятым на "Параметр N").
  - Настоящие характеристики — НЕ на самой странице товара, а на
    ОТДЕЛЬНОЙ подстранице `<product_url>characteristics/`: пары
    `<div class="... field-ex-name ...">Имя</div>` + `<div class="...
    word-break-all ...">Значение</div>` (47 настоящих пар на живой
    фикстуре: Производитель/Модель/PN/CPU/RAM/экран/порты/вес и т.д.).
    Батч-API характеристик по многим товарам сразу не найден (ни в живых
    фикстурах, ни в старых скриптах Antigravity) — только через эту
    подстраницу. needs_product_visit() == True ТОЛЬКО если GA4-данные
    раздела не дали бренд ИЛИ PN (владелец, 27.10.2026 — у большинства
    строк бренд+PN уже есть пачкой, визит нужен не всегда); candidate["url"]
    для визита — ИМЕННО characteristics-страница (product_url для ссылки
    покупателю хранится отдельно в candidate["product_url"], чтобы
    gala_writer получил ссылку на карточку товара, а не на вкладку
    характеристик).
  - Описание товара живёт на основной странице (не на characteristics/) —
    сознательно не забирается (один доп. визит на товар ради description
    не укладывается в бюджет живых запросов этого задания); description
    у kns остаётся None, пока не заведён третий визит за описанием."""
from __future__ import annotations

import re
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "kns"
BASE_URL = "https://www.kns.ru"

# Статический короткий список разделов (владелец может расширить — полный
# список разделов см. в старом harvest_kns_massive.py). Полный обход
# каталога этим заданием не запускается.
CATEGORIES: list[tuple[str, str, list[str]]] = [
    ("https://www.kns.ru/catalog/noutbuki/", "Ноутбуки", ["Оргтехника и ИТ", "Ноутбуки"]),
]

_GOODS_BLOCK_RE = re.compile(r"window\.goodsList\.push\((\{[\s\S]*?\})\);")
_FIELD_RE = re.compile(
    r"item_id:\s*'([^']+)'[\s\S]*?item_name:\s*'([^']+)'[\s\S]*?price:\s*'([^']+)'"
)
_ITEM_BRAND_RE = re.compile(r"item_brand:\s*'([^']*)'")
_ITEM_VARIANT_RE = re.compile(r"item_variant:\s*'([^']*)'")
_PRODUCT_LINK_RE = re.compile(r'href="(/product/[^"?]+/)"')
_CHAR_ROW_RE = re.compile(
    r'field-ex-name"[^>]*>\s*([^<]+?)\s*</div>\s*<div class="[^"]*word-break-all"[^>]*>(.*?)</div>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def page_url(category_url: str, page: int) -> str:
    if page <= 1:
        return category_url
    return f"{category_url}page{page}/"


def parse_category_page(html: str) -> list[dict]:
    blocks = _GOODS_BLOCK_RE.findall(html)
    # Карточки раздела идут в том же порядке, что и ссылки /product/.../ —
    # сопоставляем по порядку появления (у kns нет общего id в обоих
    # местах разметки раздела).
    product_links = []
    seen_links = set()
    for link in _PRODUCT_LINK_RE.findall(html):
        if link not in seen_links:
            seen_links.add(link)
            product_links.append(link)

    candidates = []
    for idx, block in enumerate(blocks):
        m = _FIELD_RE.search(block)
        if not m:
            continue
        item_id, name, price_raw = m.groups()
        brand_m = _ITEM_BRAND_RE.search(block)
        variant_m = _ITEM_VARIANT_RE.search(block)
        try:
            price = float(price_raw)
        except ValueError:
            price = None
        product_url = BASE_URL + product_links[idx] if idx < len(product_links) else None
        if not product_url:
            continue
        candidates.append({
            "name": name.strip(),
            "url": product_url.rstrip("/") + "/characteristics/",
            "product_url": product_url,
            "price": price,
            "store_article": item_id,
            "brand": (brand_m.group(1).strip() if brand_m and brand_m.group(1).strip() else None),
            "manufacturer_article": (variant_m.group(1).strip() if variant_m and variant_m.group(1).strip() else None),
        })
    return candidates


def needs_product_visit(candidate: dict) -> bool:
    # Бренд и артикул производителя (PN) уже приходят ПАЧКОЙ в разделе
    # (GA4 item_brand/item_variant, см. докстринг модуля) — для строки с
    # обоими полями characteristics/ подстраница нужна только ради
    # характеристик, которые необязательны для валидного item (у них уже
    # есть identity-данные). Визит оставлен ТОЛЬКО если GA4 не дал бренд
    # или артикул — тогда характеристики (где внутри таблицы тоже есть
    # "Производитель"/"PN") становятся единственным способом их добрать.
    return not (candidate.get("brand") and candidate.get("manufacturer_article"))


def parse_product_page(html: str, url: str) -> dict:
    characteristics = []
    manufacturer_article = None
    brand = None
    for name, value_html in _CHAR_ROW_RE.findall(html):
        value = _TAG_RE.sub("", value_html).strip()
        name = name.strip()
        if not name or not value:
            continue
        characteristics.append({"name": name, "value": value, "unit": None, "in_description": False})
        name_lower = name.lower()
        if name_lower == "pn" and not manufacturer_article:
            manufacturer_article = value
        elif name_lower == "производитель" and not brand:
            brand = value
    return {
        "characteristics": characteristics,
        "manufacturer_article": manufacturer_article,
        "brand": brand,
    }


def build_item(candidate: dict, enrichment: dict, known_brands: set) -> Optional[dict]:
    name = candidate.get("name")
    if not name:
        return None
    url = candidate.get("product_url")
    characteristics = enrichment.get("characteristics") or []
    brand = candidate.get("brand") or enrichment.get("brand")
    manufacturer_article = candidate.get("manufacturer_article") or enrichment.get("manufacturer_article")

    manufacturer = gala_writer.resolve_manufacturer(
        name, brand, characteristics, known_brands,
    )

    return gala_writer.build_item(
        name=name,
        unit="шт",
        price=candidate.get("price"),
        currency="RUB" if candidate.get("price") is not None else None,
        manufacturer=manufacturer,
        manufacturer_article=manufacturer_article,
        store_article=candidate.get("store_article"),
        characteristics=characteristics,
        links=[{"url": url, "price": candidate.get("price")}] if url else [],
        source_url=url,
        source_id=candidate.get("store_article"),
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
    # Старый harvest_kns_massive.py был однопоточным (sleep 0.4-1с, без
    # ThreadPoolExecutor) и НИКОГДА не заходил на товар — характеристики
    # у него были "Параметр N" из описания. needs_product_visit теперь
    # заходит только когда GA4 не дал бренд/PN (редкая строка).
    concurrency=1,
    default_pause_per_domain=0.4,
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
