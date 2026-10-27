"""Сборщик k-spasatel.ru. Только парсинг HTML этого магазина — цикл
обхода разделов/товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

Проверено на живых фикстурах (tools/harvest/tests/fixtures/k_spasatel_*.html,
27.10.2026, 3 живых запроса — 1 раздел + 2 товара):
  - Нет JSON-LD ни на разделе, ни на товаре — весь парсинг по HTML-разметке
    магазина (Opencart-подобный шаблон).
  - Страница РАЗДЕЛА: ссылки на товары —
    `<div class="products__item-image">...<a href="<URL товара без /
    на конце>">` — URL абсолютный, отдельного артикула/бренда в разделе
    нет (нужен визит на товар).
  - Страница ТОВАРА: `<span class="js-product-code">302614</span>` — это
    артикул САМОГО k-spasatel (store_article), НЕ производителя —
    отдельного поля артикула производителя на живых фикстурах не найдено,
    поэтому manufacturer_article всегда None (брак старого
    harvest_all_kspasatel_nomenclature.py: он при отсутствии цены/артикула
    из специфичной разметки дёргал артикул из URL-слага — это не артикул,
    а транслитерация названия).
  - Цена: на ОБЕИХ живых фикстурах блок `<div class="list_price">` отдаёт
    "Цена по запросу" без числа (`<h2>Цена по запросу</h2>`, без
    `itemprop="price"` и без числового span) — похоже, k-spasatel прячет
    цену у значимой доли каталога (возможно, оптовый прайс через заявку).
    Для таких строк price=None, has_price=False — не угадывать цену по
    старому fallback-регексу (брак старого сборщика, искавшего ЛЮБОЕ
    число перед "руб"/"₽" в любом блоке с классом price, что на страницах
    без цены находило случайные цифры из разметки).
  - Настоящие характеристики — пары внутри `id="tab-description"` в ДВУХ
    форматах шаблона (разные для разных типов товара, оба видны на живых
    фикстурах): `<p>Имя:&nbsp;Значение</p>` (байдарка) и
    `<table><tr><td>Имя</td><td>Значение</td></tr></table>` (мотор/доска).
    Оба формата разбираются раздельными регексами ниже — НЕ единым
    "развалить description по запятым" (брак старого сборщика)."""
from __future__ import annotations

import re
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "k_spasatel"
BASE_URL = "https://k-spasatel.ru"

# Статический короткий список разделов (владелец может расширить — полный
# список берётся с главной страницы в discover_categories()). Полный обход
# каталога этим заданием не запускается.
CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "https://k-spasatel.ru/dlja-spasenija-na-vode/lodki/",
        "Лодки",
        ["Средства спасения на водах", "Лодки"],
    ),
]

_PRODUCT_LINK_RE = re.compile(
    r'products__item-image">\s*<a href="(https://k-spasatel\.ru/[^"#?]+)"'
)
_H1_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>")
_PRODUCT_CODE_RE = re.compile(r'js-product-code">([^<]+)<')
_IMG_RE = re.compile(r'<img[^>]+src="([^"]*catalog/[^"]+\.(?:jpg|jpeg|png|webp))"', re.I)
_PRICE_VALUE_RE = re.compile(r'itemprop="price"[^>]*content="([\d.]+)"')
_SPEC_P_RE = re.compile(r"<p>\s*([^<:]{2,60}?):&nbsp;([^<]{1,150})</p>")
_SPEC_TABLE_ROW_RE = re.compile(
    r"<tr>\s*<td>([^<]{2,60})</td>\s*<td>([^<]{1,150})</td>\s*</tr>", re.DOTALL
)


def page_url(category_url: str, page: int) -> str:
    if page <= 1:
        return category_url
    return f"{category_url}?page={page}"


def parse_category_page(html: str) -> list[dict]:
    seen = set()
    candidates = []
    for url in _PRODUCT_LINK_RE.findall(html):
        if url in seen:
            continue
        seen.add(url)
        candidates.append({"name": None, "url": url})
    return candidates


def needs_product_visit(candidate: dict) -> bool:
    # В разделе нет ни названия, ни цены, ни характеристик — визит всегда
    # обязателен.
    return True


def _extract_characteristics(html: str) -> list[dict]:
    desc_block_m = re.search(r'id="tab-description">([\s\S]*?)<div class="section_elem" id="tab-review"', html)
    desc_html = desc_block_m.group(1) if desc_block_m else html

    characteristics = []
    for name, value in _SPEC_P_RE.findall(desc_html):
        name, value = name.strip(), value.strip()
        if name and value:
            characteristics.append({"name": name, "value": value, "unit": None, "in_description": False})
    if not characteristics:
        for name, value in _SPEC_TABLE_ROW_RE.findall(desc_html):
            name, value = name.strip(), value.strip()
            if name and value:
                characteristics.append({"name": name, "value": value, "unit": None, "in_description": False})
    return characteristics


def parse_product_page(html: str, url: str) -> dict:
    h1 = _H1_RE.search(html)
    name = h1.group(1).strip() if h1 else None

    code_m = _PRODUCT_CODE_RE.search(html)
    store_article = code_m.group(1).strip() if code_m else None

    price_m = _PRICE_VALUE_RE.search(html)
    price = float(price_m.group(1)) if price_m else None

    images = []
    for img in _IMG_RE.findall(html):
        full = img if img.startswith("http") else BASE_URL + "/" + img.lstrip("/")
        if full not in images:
            images.append(full)

    return {
        "name": name,
        "store_article": store_article,
        "price": price,
        "photos": images[:3],
        "characteristics": _extract_characteristics(html),
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
