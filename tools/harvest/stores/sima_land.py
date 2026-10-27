"""Сборщик sima-land.ru. Только парсинг JSON этого магазина — цикл обхода
разделов/товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

Проверено на живой фикстуре (tools/harvest/tests/fixtures/sima_category.json,
27.10.2026, 1 живой запрос — ниже бюджета в 3 страницы, см. ниже почему):
  - sima-land отдаёт каталог через собственный JSON API
    `https://www.sima-land.ru/api/v3/item/?category_id=<id>&page=<n>&per-page=50`
    (НЕ HTML, НЕ JSON-LD) — ответ `{"items": [...], "_meta": {...}}`.
  - КАЖДЫЙ элемент `items[]` УЖЕ несёт всё, что нужно для строки:
    `trademark.name` — бренд (НЕ сам sima-land, который старый
    harvest_sima_land_resilient.py подставлял по умолчанию — брак, см.
    ПРАВИЛО №6/докстрин gala_writer: нет trademark → manufacturer=None, не
    "Сима-ленд"), `country.name` — страна (country_id переведён магазином),
    `sid` — артикул САМОГО sima-land (store_article, не производителя —
    отдельного поля артикула производителя в этом API нет, поэтому
    manufacturer_article всегда None), `size`/`stuff` — настоящие
    характеристики (размеры и материал), `price`/`weight`/`okpd2`.
  - Так как вся карточка уже в ответе раздела, посещать страницу товара НЕ
    нужно НИКОГДА — needs_product_visit() всегда False, parse_product_page
    не вызывается ни разу за реальный прогон. Поэтому для фикстур хватило
    ОДНОГО живого запроса (категория целиком даёт и "карточку", и "товар"),
    а не трёх — второй/третий живой запрос было бы на что тратить нечего,
    чем предписанный лимит и не использован.
  - Темп запросов владелец велел поднять с 0,2 с (старый сборщик) до 1 с —
    это делает core.http.HttpClient (pause_per_domain=1.0 по умолчанию,
    run.py его не переопределяет)."""
from __future__ import annotations

import json
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "sima_land"
PER_PAGE = 50

# Статический короткий список разделов (владелец может расширить по
# category_id из https://www.sima-land.ru/api/v3/category/). Полный обход
# каталога этим заданием не запускается.
CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "https://www.sima-land.ru/api/v3/item/?category_id=2",
        "Бижутерия",
        ["Бижутерия и аксессуары", "Бижутерия"],
    ),
]


def page_url(category_url: str, page: int) -> str:
    return f"{category_url}&page={page}&per-page={PER_PAGE}"


def _characteristics_from(item: dict) -> list[dict]:
    characteristics = []
    size = (item.get("size") or "").strip()
    if size:
        characteristics.append({"name": "Размер", "value": size, "unit": None, "in_description": False})
    stuff = (item.get("stuff") or "").strip()
    if stuff:
        characteristics.append({"name": "Материал", "value": stuff, "unit": None, "in_description": False})
    weight = item.get("weight")
    if weight:
        characteristics.append({"name": "Вес", "value": str(weight), "unit": "г", "in_description": False})
    return characteristics


def parse_category_page(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    candidates = []
    for item in data.get("items", []):
        name = (item.get("name") or "").strip()
        sid = item.get("sid")
        item_url = item.get("itemUrl")
        if not name or not sid:
            continue
        url = f"https://www.sima-land.ru{item_url}" if item_url else f"https://www.sima-land.ru/{sid}/"
        trademark = item.get("trademark") or {}
        country = item.get("country") or {}
        candidates.append({
            "name": name,
            "url": url,
            "price": item.get("price"),
            "photos": [item.get("photoUrl")] if item.get("photoUrl") else [],
            "store_article": str(sid),
            "trademark_name": (trademark.get("name") or "").strip() or None,
            "country_name": (country.get("name") or "").strip() or None,
            "unit_name": "шт",
            "okpd2": item.get("okpd2"),
            "characteristics": _characteristics_from(item),
        })
    return candidates


def needs_product_visit(candidate: dict) -> bool:
    # Вся карточка уже в ответе раздела (см. докстринг модуля) — страница
    # товара не нужна никогда.
    return False


def parse_product_page(html: str, url: str) -> dict:  # pragma: no cover - не вызывается
    return {}


def build_item(candidate: dict, enrichment: dict, known_brands: set) -> Optional[dict]:
    name = candidate.get("name")
    if not name:
        return None
    url = candidate.get("url")
    characteristics = candidate.get("characteristics") or []

    manufacturer = gala_writer.resolve_manufacturer(
        name, candidate.get("trademark_name"), characteristics, known_brands,
    )

    return gala_writer.build_item(
        name=name,
        unit=candidate.get("unit_name") or "шт",
        price=candidate.get("price"),
        currency="RUB" if candidate.get("price") is not None else None,
        manufacturer=manufacturer,
        manufacturer_article=None,
        store_article=candidate.get("store_article"),
        characteristics=characteristics,
        photos=candidate.get("photos"),
        links=[{"url": url, "price": candidate.get("price")}] if url else [],
        source_url=url,
        source_id=candidate.get("store_article"),
        country_origin=candidate.get("country_name"),
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
