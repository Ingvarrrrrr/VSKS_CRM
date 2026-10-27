"""Сборщик baucenter.ru. Только парсинг Next.js data-JSON этого магазина —
цикл обхода разделов/товаров, троттлинг, чекпоинт и сборка item живут в
tools.harvest.core.runner / gala_writer (ПРАВИЛО №5/№6).

Проверено на живых фикстурах (tools/harvest/tests/fixtures/baucenter_*.json,
27.10.2026, 3 живых запроса — 1 категория + 2 товара; buildId и sitemap
раздела были только для подбора РЕАЛЬНОГО слага листовой категории, сами
данные товара из них не брались):
  - Раздел — Next.js data-роут `https://baucenter.ru/_next/data/<buildId>/
    catalog/<leaf-slug>.json` (buildId — из `__NEXT_DATA__` на главной,
    меняется при деплое сайта — DISCOVER_BUILD_ID ниже получает его живым
    запросом перед сбором, а не хардкодит). Ответ — `pageProps.initialState.
    products.{list,count}`. list[] уже несёт `brand` (строка бренда прямо в
    листинге, например "Церезит") — поэтому бренд берём из раздела, НЕ
    угадываем по названию (брак старого pull_baucenter_bulk.py, который в
    остальном верно читал это поле, но не читал characteristics/country).
  - `article` в list[] — артикул САМОГО baucenter (совпадает с числом на
    конце `url`), это store_article, НЕ артикул производителя — отдельного
    поля артикула производителя нет ни в листинге, ни на странице товара,
    поэтому manufacturer_article всегда None (не путать со старым
    enrich_baucenter_all.py, который вообще не разделял эти два артикула).
  - `price.main.price` — целое число В КОПЕЙКАХ (114900 = 1149 ₽) —
    делить на 100 ВСЕГДА, не только когда > 1000, как делал старый
    enrich_baucenter_all.py (у дешёвых товаров это давало неверную цену).
  - Страница товара — `https://baucenter.ru/_next/data/<buildId>/product/
    <slug-с-article-в-конце>.json` → `pageProps.initialState.product.
    currentProductData.product` — `properties[]` ({code,title,value}) это
    настоящие характеристики (используем title/value, НЕ код); страна —
    свойство с title, начинающимся на "Страна" (код на живой фикстуре был
    COUNTRY_OF_ORIGIN, но у старого enrich_baucenter_all.py искавшего код
    STRANA_PROIZVODSTVA код расходится по категориям — match по тексту
    title надёжнее кода). needs_product_visit() всегда True — характеристики
    и страна есть только на странице товара."""
from __future__ import annotations

import html as _html
import json
import re
from typing import Optional

from tools.harvest.core import gala_writer
from tools.harvest.core.http import HttpClient
from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "baucenter"
BASE_URL = "https://baucenter.ru"
_FALLBACK_BUILD_ID = "lCk8p3TEBrSa1BteCoW7A"

# Статический короткий список листовых разделов — по одному на каждую из
# трёх требуемых выгрузок (стройка / электрика-освещение / инструмент).
# Слаги взяты с живого sitemap_iblock_2_sections.xml (27.10.2026), владелец
# может расширить список/заменить на дискавери по тому же sitemap.
CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "catalog/stroitelnye-gruntovki-ctg-36829-30816-29124",
        "Грунтовки строительные",
        ["Стройматериалы", "Грунтовки"],
    ),
    (
        "catalog/schetchiki-elektroenergii-ctg-29228-29282-29286",
        "Счётчики электроэнергии",
        ["Электрика и освещение", "Электрощитовое оборудование"],
    ),
    (
        "catalog/stolyarnyy-slesarnyy-instrument-ctg-29290-29302",
        "Столярный и слесарный инструмент",
        ["Инструмент", "Столярно-слесарный"],
    ),
]

_COUNTRY_TITLE_RE = re.compile(r"^страна", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def discover_build_id(client: HttpClient) -> str:
    """Живой запрос главной страницы за текущим buildId (меняется при
    деплое Next.js-сборки сайта) — вызывается явно перед настоящим
    прогоном, не на импорте модуля и не в тестах (фикстуры используют
    buildId только как часть URL, сам JSON от него не зависит)."""
    html_text = client.fetch(BASE_URL + "/")
    if html_text:
        m = re.search(r'"buildId":"([^"]+)"', html_text)
        if m:
            return m.group(1)
    return _FALLBACK_BUILD_ID


def page_url(category_slug: str, page: int) -> str:
    base = f"{BASE_URL}/_next/data/{{build_id}}/{category_slug}.json"
    if page > 1:
        base += f"?page={page}"
    return base


def make_page_url(build_id: str):
    def _page_url(category_slug: str, page: int) -> str:
        return page_url(category_slug, page).format(build_id=build_id)
    return _page_url


def _clean_description(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    text = _TAG_RE.sub(" ", raw)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def parse_category_page(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    products = data.get("pageProps", {}).get("initialState", {}).get("products", {})
    candidates = []
    for p in products.get("list", []):
        title = (p.get("title") or "").strip()
        rel_url = p.get("url")
        if not title or not rel_url:
            continue
        price_main = (p.get("price") or {}).get("main") or {}
        kopecks = price_main.get("price")
        price = round(kopecks / 100.0, 2) if isinstance(kopecks, (int, float)) else None
        images = [img.get("path") for img in p.get("images") or [] if img.get("path")]
        candidates.append({
            "name": title,
            "url": BASE_URL + rel_url if rel_url.startswith("/") else rel_url,
            "price": price,
            "photos": images,
            "store_article": str(p.get("article")) if p.get("article") else None,
            "brand": (p.get("brand") or "").strip() or None,
        })
    return candidates


def needs_product_visit(candidate: dict) -> bool:
    # Характеристики и страна происхождения есть только на странице
    # товара (листинг их не несёт) — визит нужен всегда.
    return True


def parse_product_page(html_text: str, url: str) -> dict:
    try:
        data = json.loads(html_text)
    except (json.JSONDecodeError, ValueError):
        return {}
    product = (
        data.get("pageProps", {})
        .get("initialState", {})
        .get("product", {})
        .get("currentProductData", {})
        .get("product", {})
    )
    characteristics = []
    country = None
    for prop in product.get("properties") or []:
        title = (prop.get("title") or "").strip()
        value = (prop.get("value") or "").strip()
        if not title or not value:
            continue
        characteristics.append({"name": title, "value": value, "unit": None, "in_description": False})
        if _COUNTRY_TITLE_RE.match(title):
            country = value
    return {
        "brand": (product.get("brand") or "").strip() or None,
        "characteristics": characteristics,
        "description": _clean_description(product.get("description")),
        "country_origin": country,
    }


def build_item(candidate: dict, enrichment: dict, known_brands: set) -> Optional[dict]:
    name = candidate.get("name")
    if not name:
        return None
    url = candidate.get("url")
    characteristics = enrichment.get("characteristics") or []
    brand = enrichment.get("brand") or candidate.get("brand")

    manufacturer = gala_writer.resolve_manufacturer(
        name, brand, characteristics, known_brands,
    )

    return gala_writer.build_item(
        name=name,
        unit="шт",
        price=candidate.get("price"),
        currency="RUB" if candidate.get("price") is not None else None,
        manufacturer=manufacturer,
        manufacturer_article=None,
        store_article=candidate.get("store_article"),
        description=enrichment.get("description"),
        characteristics=characteristics,
        photos=candidate.get("photos"),
        links=[{"url": url, "price": candidate.get("price")}] if url else [],
        source_url=url,
        source_id=candidate.get("store_article"),
        country_origin=enrichment.get("country_origin"),
        seller_inn=gala_writer.seller_inn_for(url),
    )


SPEC = StoreSpec(
    name=STORE_NAME,
    categories=CATEGORIES,
    page_url=page_url,  # переопределяется в harvest() на фактический build_id
    parse_category_page=parse_category_page,
    needs_product_visit=needs_product_visit,
    parse_product_page=parse_product_page,
    build_item=build_item,
    max_pages_per_category=3,
)


def harvest(out_path: str, limit_categories: Optional[int] = None, resume: bool = False, pause_per_domain: float = 1.0) -> dict:
    client = HttpClient(STORE_NAME, pause_per_domain=pause_per_domain)
    build_id = discover_build_id(client)
    spec = SPEC
    spec.page_url = make_page_url(build_id)
    return _run_harvest(spec, out_path, limit_categories=limit_categories, resume=resume, pause_per_domain=pause_per_domain)
