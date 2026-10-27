"""Сборщик safe.ru (завод ПРОМЕТ). Только парсинг HTML этого магазина —
цикл обхода разделов/товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

Проверено на живых фикстурах (tools/harvest/tests/fixtures/safe_*.html,
27.10.2026, 4 живых запроса — верхний раздел для поиска реального
листового слага + 1 листовой раздел + 2 товара; каталог safe.ru
двухуровневый — /catalog/metallicheskie-stellazhi/ сам по себе не выдаёт
карточки товара, только ссылки на листовые подразделы):
  - Листовой раздел: ссылки `href="/products/<slug>/"`.
  - Страница товара (Bitrix): `<meta itemprop="price" content="4750">`
    внутри `itemprop="offers"` — настоящая цена (НЕ регекс по тексту
    "руб"/"₽", как у старого harvest_all_safe_ru.py, который на некоторых
    шаблонах страницы ловил случайные числа).
  - Настоящие характеристики — `<div class="card__characteristics">`
    → `<table id="table1"><tr><td>Имя:</td><td>Значение</td></tr>` — ЕСТЬ
    строки `Производитель: ПРОМЕТ` и `Страна: Россия` ПРЯМО В ТАБЛИЦЕ на
    ОБЕИХ живых фикстурах — берём бренд и страну ИМЕННО отсюда, а НЕ
    хардкодим "ПРАКТИК (ПРОМЕТ)" как делал старый harvest_all_safe_ru.py
    (неточное имя бренда — реальное поле отдаёт просто "ПРОМЕТ").
  - Отдельного поля "Артикул" на живых фикстурах нет вообще (не только
    в таблице характеристик — по всей странице). store_article берём из
    `data-id="<id>"` на кнопке "В список покупок" (внутренний ID товара
    Bitrix, например "818"/"998") — это честный внутренний код магазина,
    НЕ артикул производителя (его отдельного поля нет, manufacturer_article
    всегда None, в отличие от старого сборщика, который при отсутствии
    артикула генерировал его из URL-слага — слаг это не артикул)."""
from __future__ import annotations

import re
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "safe"
BASE_URL = "https://www.safe.ru"

# Статический короткий список листовых разделов (владелец может
# расширить — подразделы видны на корневых страницах
# /catalog/<root>/, см. docstring). Полный обход каталога этим
# заданием не запускается.
CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "https://www.safe.ru/catalog/metallicheskie-stellazhi/ms-standart-500-kg-na-sektsiyu/",
        "Стеллажи MS Standart (500 кг на секцию)",
        ["Металлическая мебель и стеллажи", "Стеллажи MS Standart"],
    ),
]

_PRODUCT_LINK_RE = re.compile(r'href="(/products/[^"]+/)"')
_H1_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>")
_PRICE_RE = re.compile(r'itemprop="price"\s+content="([\d.]+)"')
_DATA_ID_RE = re.compile(r'data-id="(\d+)"')
_TABLE_RE = re.compile(r'id="table1">([\s\S]*?)</table>')
_ROW_RE = re.compile(r"<td>([^<]+)</td>\s*<td>([^<]*)</td>")


def page_url(category_url: str, page: int) -> str:
    if page <= 1:
        return category_url
    return f"{category_url}?PAGEN_1={page}"


def parse_category_page(html: str) -> list[dict]:
    seen = set()
    candidates = []
    for rel in _PRODUCT_LINK_RE.findall(html):
        url = BASE_URL + rel
        if url not in seen:
            seen.add(url)
            candidates.append({"name": None, "url": url})
    return candidates


def needs_product_visit(candidate: dict) -> bool:
    return True


def parse_product_page(html: str, url: str) -> dict:
    h1 = _H1_RE.search(html)
    name = h1.group(1).strip() if h1 else None

    price_m = _PRICE_RE.search(html)
    price = float(price_m.group(1)) if price_m else None

    data_id_m = _DATA_ID_RE.search(html)
    store_article = data_id_m.group(1) if data_id_m else None

    characteristics = []
    brand = None
    country = None
    table_m = _TABLE_RE.search(html)
    if table_m:
        for raw_name, raw_value in _ROW_RE.findall(table_m.group(1)):
            name_clean = raw_name.strip().rstrip(":").strip()
            value_clean = raw_value.strip()
            if not name_clean or not value_clean:
                continue
            characteristics.append({"name": name_clean, "value": value_clean, "unit": None, "in_description": False})
            name_lower = name_clean.lower()
            if name_lower == "производитель":
                brand = value_clean
            elif name_lower == "страна":
                country = value_clean

    return {
        "name": name,
        "price": price,
        "store_article": store_article,
        "jsonld_brand": brand,
        "characteristics": characteristics,
        "country_origin": country,
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
)


def harvest(out_path: str, limit_categories: Optional[int] = None, resume: bool = False, pause_per_domain: float = 1.0) -> dict:
    return _run_harvest(SPEC, out_path, limit_categories=limit_categories, resume=resume, pause_per_domain=pause_per_domain)
