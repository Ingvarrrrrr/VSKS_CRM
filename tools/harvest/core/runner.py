"""Общий цикл обхода разделов/товаров магазина (ПРАВИЛО №5 — store-модули
только парсят HTML/JSON конкретного магазина и объявляют StoreSpec; цикл
пагинации, чекпоинт, троттлинг/concurrency, инкремент по --previous,
режим --prices-only и сохранение живут здесь один раз)."""
from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

from tools.harvest.core import checkpoint, gala_writer
from tools.harvest.core.http import HttpClient, StoreAbortedError

DEFAULT_MAX_PAGES_PER_CATEGORY = 5


@dataclass
class StoreSpec:
    """Контракт, который объявляет каждый tools/harvest/stores/<store>.py.

    categories: список (category_url, category_name, category_path: list[str]).
    page_url(category_url, page) -> URL страницы раздела (page начинается с 1).
    parse_category_page(html) -> список кандидатов-dict (минимум name/url,
        остальное — что нашлось в пакетном источнике раздела: price/photos/
        source_id/brand/characteristics — см. докстринг конкретного
        stores/<store>.py, где именно перечислено, что раздел несёт пачкой).
    needs_product_visit(candidate) -> True, если ни в одном пакетном
        источнике (раздел/API списка/API товара пачкой) не хватает данных
        (бренд/артикул производителя/настоящие характеристики) и нужно
        зайти на страницу/API-эндпойнт конкретного товара.
    parse_product_page(html, url) -> dict обогащения (jsonld_brand,
        manufacturer_article, characteristics, country_origin, ...) —
        конкретные ключи решает build_item.
    build_item(candidate, enrichment, known_brands) -> dict item (через
        gala_writer.build_item) или None, если строку решено не включать.
    concurrency: сколько параллельных запросов на товарные страницы этого
        магазина допустимо (по образцу старого сборщика этого магазина —
        см. docstring stores/<store>.py; 1 — старый сборщик был
        однопоточным). per-store, не глобально (core/http.py сам троттлинг
        не выбирает).
    default_pause_per_domain: пауза между запросами при concurrency==1,
        секунды (используется, если CLI не передал свою через
        --pause-per-domain).
    category_has_price: раздел/API списка этого магазина отдаёт цену сразу
        (без визита на товар). Если False — режим --prices-only для этого
        магазина честно не может дать свежую цену без визита (см.
        docstring stores/<store>.py и README)."""

    name: str
    categories: list[tuple[str, str, list[str]]]
    page_url: Callable[[str, int], str]
    parse_category_page: Callable[[str], list[dict]]
    needs_product_visit: Callable[[dict], bool]
    parse_product_page: Callable[[str, str], dict]
    build_item: Callable[[dict, dict, set], Optional[dict]]
    max_pages_per_category: int = DEFAULT_MAX_PAGES_PER_CATEGORY
    concurrency: int = 1
    default_pause_per_domain: float = 1.0
    category_has_price: bool = True
    # True — у этого магазина needs_product_visit() по умолчанию не требует
    # визита (все ОБЯЗАТЕЛЬНЫЕ поля даёт раздел), а визит даёт только
    # необязательные "подробности" (характеристики/точный артикул) — такой
    # визит включается флагом CLI --with-details (владелец, 27.10.2026,
    # regard — первый сборщик с этим режимом).
    supports_details: bool = False


def _load_existing_items(out_path: str) -> list[dict]:
    if not os.path.exists(out_path):
        return []
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        return list(existing.get("items", []))
    except Exception:
        return []


def _candidate_match_url(candidate: dict) -> Optional[str]:
    """URL человекочитаемой карточки товара для сопоставления с --previous
    (НЕ candidate["url"], который у kns/ice_age — адрес служебного
    API/подстраницы характеристик, а не ссылка покупателю)."""
    return candidate.get("product_url") or candidate.get("url")


def _index_previous_items(previous_items: list[dict]) -> dict[str, dict]:
    by_url: dict[str, dict] = {}
    for item in previous_items:
        urls = set()
        source_url = item.get("source_url")
        if source_url:
            urls.add(source_url)
        for link in item.get("links") or []:
            u = link.get("url")
            if u:
                urls.add(u)
        for u in urls:
            by_url[u] = item
    return by_url


def _is_complete_previous(item: dict) -> bool:
    """Прошлая строка несёт достаточно данных, чтобы НЕ открывать товар
    повторно (владелец, п.2 задания 27.10.2026): есть бренд И (настоящие
    характеристики ИЛИ описание)."""
    if not item.get("manufacturer"):
        return False
    return bool(item.get("characteristics") or item.get("description"))


def _item_from_previous(previous_item: dict, candidate: dict, today: str) -> dict:
    """Клонирует прошлую строку, обновляя ТОЛЬКО цену/наличие/дату из
    свежего кандидата раздела — остальные поля (бренд/характеристики/
    описание/артикул) не трогаются (владелец, п.2: "не открывается
    повторно")."""
    item = dict(previous_item)
    url = _candidate_match_url(candidate) or item.get("source_url")
    new_price = candidate.get("price")
    if new_price is not None:
        item["price"] = new_price
        item["price_date"] = today
        item["currency"] = "RUB"
    if url:
        item["links"] = [{"url": url, "price": item.get("price")}]
        item["source_url"] = url
    return item


def harvest(
    spec: StoreSpec,
    out_path: str,
    limit_categories: Optional[int] = None,
    resume: bool = False,
    pause_per_domain: Optional[float] = None,
    previous_items: Optional[list[dict]] = None,
    prices_only: bool = False,
    with_details: bool = False,
) -> dict:
    """Обходит разделы spec.categories, собирает items в манифест
    gala-catalog и возвращает его (запись файла — отдельный шаг, через
    core.quality.write_catalog, не здесь — ПРАВИЛО №6: один гейт перед
    записью, не внутри цикла сбора).

    previous_items: прошлый gala-каталог этого магазина (--previous) —
    товары с уже полными данными не открываются повторно (см.
    _is_complete_previous/_item_from_previous).
    prices_only: товарные страницы НЕ открываются вовсе (needs_product_visit
    игнорируется) — для магазинов, где раздел не несёт цену
    (spec.category_has_price=False), печатается честное предупреждение, и
    такие строки берут цену только из --previous (может быть устаревшей).
    with_details: у магазинов с spec.supports_details=True (раздел уже даёт
    все ОБЯЗАТЕЛЬНЫЕ поля, needs_product_visit по умолчанию не требует
    визита) включает визит ради необязательных "подробностей"
    (характеристики/точный артикул) — игнорируется, если prices_only=True."""
    effective_pause = pause_per_domain if pause_per_domain is not None else spec.default_pause_per_domain
    client = HttpClient(spec.name, pause_per_domain=effective_pause, concurrency=spec.concurrency)
    ckpt_path = checkpoint.checkpoint_path(out_path)
    processed = checkpoint.load_processed(ckpt_path) if resume else set()

    manifest = gala_writer.build_manifest(spec.name, os.path.basename(out_path))
    items = manifest["items"]
    if resume:
        items.extend(_load_existing_items(out_path))

    previous_by_url = _index_previous_items(previous_items or [])
    today = _dt.date.today().isoformat()

    if prices_only and not spec.category_has_price:
        print(
            f"[{spec.name}] --prices-only: цена этого магазина есть ТОЛЬКО на "
            f"странице товара — страницы не открываются (режим запрещает), "
            f"цена берётся из --previous и может быть устаревшей."
        )

    categories = spec.categories[:limit_categories] if limit_categories else spec.categories

    try:
        for cat_url, cat_name, cat_path in categories:
            if cat_url in processed:
                continue
            cat_added = 0
            for page in range(1, spec.max_pages_per_category + 1):
                page_url = spec.page_url(cat_url, page)
                html = client.fetch(page_url)
                if not html:
                    checkpoint.append_line(ckpt_path, page_url, "category", "fail")
                    break

                candidates = spec.parse_category_page(html)
                if not candidates:
                    checkpoint.append_line(ckpt_path, page_url, "category", "ok")
                    break

                fresh_candidates = []
                for candidate in candidates:
                    purl = candidate.get("url")
                    if not purl or purl in processed:
                        continue
                    fresh_candidates.append(candidate)

                # Шаг 1: прошлые полные строки — без визита вообще.
                to_visit: list[dict] = []
                resolved: list[tuple[dict, dict]] = []  # (candidate, enrichment) без визита
                for candidate in fresh_candidates:
                    match_url = _candidate_match_url(candidate)
                    prev = previous_by_url.get(match_url) if match_url else None
                    if prev is not None and _is_complete_previous(prev):
                        item = _item_from_previous(prev, candidate, today)
                        items.append(item)
                        cat_added += 1
                        processed.add(candidate.get("url"))
                        checkpoint.append_line(ckpt_path, candidate.get("url"), "product", "skip-previous")
                        continue
                    if prices_only:
                        resolved.append((candidate, {}))
                        continue
                    wants_details = with_details and spec.supports_details
                    if spec.needs_product_visit(candidate) or wants_details:
                        to_visit.append(candidate)
                    else:
                        resolved.append((candidate, {}))

                # Шаг 2: батч живых визитов (до spec.concurrency параллельно).
                visit_urls = [c.get("url") for c in to_visit]
                fetched = client.fetch_many(visit_urls) if visit_urls else {}
                for candidate in to_visit:
                    purl = candidate.get("url")
                    phtml = fetched.get(purl)
                    if phtml:
                        enrichment = spec.parse_product_page(phtml, purl)
                        checkpoint.append_line(ckpt_path, purl, "product", "ok")
                    else:
                        enrichment = {}
                        checkpoint.append_line(ckpt_path, purl, "product", "fail")
                    resolved.append((candidate, enrichment))

                # Шаг 3: сборка item для всех, кто не взят из --previous.
                for candidate, enrichment in resolved:
                    known_brands = gala_writer.KNOWN_BRANDS_SEED | gala_writer.known_brands_from_items(items)
                    item = spec.build_item(candidate, enrichment, known_brands)
                    if item:
                        items.append(item)
                        cat_added += 1
                    processed.add(candidate.get("url"))

                checkpoint.append_line(ckpt_path, page_url, "category", "ok")

            processed.add(cat_url)
            print(f"[{spec.name}] {cat_name}: +{cat_added} (всего {len(items)})")

    except StoreAbortedError as e:
        print(f"[{spec.name}] остановлено: {e}")

    return manifest
