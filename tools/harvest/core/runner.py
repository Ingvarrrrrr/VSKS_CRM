"""Общий цикл обхода разделов/товаров магазина (ПРАВИЛО №5 — store-модули
только парсят HTML/JSON-LD конкретного магазина и объявляют StoreSpec; цикл
пагинации, чекпоинт, троттлинг и сохранение живут здесь один раз)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
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
        остальное — что нашлось в JSON-LD раздела: price/photos/source_id).
    needs_product_visit(candidate) -> True, если по кандидату не хватает
        данных (бренд/артикул производителя/настоящие характеристики) и нужно
        зайти на страницу товара.
    parse_product_page(html, url) -> dict обогащения (jsonld_brand,
        manufacturer_article, characteristics, country_origin, ...) —
        конкретные ключи решает build_item.
    build_item(candidate, enrichment, known_brands) -> dict item (через
        gala_writer.build_item) или None, если строку решено не включать.
    """

    name: str
    categories: list[tuple[str, str, list[str]]]
    page_url: Callable[[str, int], str]
    parse_category_page: Callable[[str], list[dict]]
    needs_product_visit: Callable[[dict], bool]
    parse_product_page: Callable[[str, str], dict]
    build_item: Callable[[dict, dict, set], Optional[dict]]
    max_pages_per_category: int = DEFAULT_MAX_PAGES_PER_CATEGORY


def _load_existing_items(out_path: str) -> list[dict]:
    if not os.path.exists(out_path):
        return []
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        return list(existing.get("items", []))
    except Exception:
        return []


def harvest(
    spec: StoreSpec,
    out_path: str,
    limit_categories: Optional[int] = None,
    resume: bool = False,
    pause_per_domain: float = 1.0,
) -> dict:
    """Обходит разделы spec.categories, собирает items в манифест
    gala-catalog и возвращает его (запись файла — отдельный шаг, через
    core.quality.write_catalog, не здесь — ПРАВИЛО №6: один гейт перед
    записью, не внутри цикла сбора)."""
    client = HttpClient(spec.name, pause_per_domain=pause_per_domain)
    ckpt_path = checkpoint.checkpoint_path(out_path)
    processed = checkpoint.load_processed(ckpt_path) if resume else set()

    manifest = gala_writer.build_manifest(spec.name, os.path.basename(out_path))
    items = manifest["items"]
    if resume:
        items.extend(_load_existing_items(out_path))

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

                for candidate in candidates:
                    purl = candidate.get("url")
                    if not purl or purl in processed:
                        continue

                    enrichment: dict = {}
                    if spec.needs_product_visit(candidate):
                        phtml = client.fetch(purl)
                        if phtml:
                            enrichment = spec.parse_product_page(phtml, purl)
                            checkpoint.append_line(ckpt_path, purl, "product", "ok")
                        else:
                            checkpoint.append_line(ckpt_path, purl, "product", "fail")

                    known_brands = gala_writer.KNOWN_BRANDS_SEED | gala_writer.known_brands_from_items(items)
                    item = spec.build_item(candidate, enrichment, known_brands)
                    if item:
                        items.append(item)
                        cat_added += 1
                    processed.add(purl)

                checkpoint.append_line(ckpt_path, page_url, "category", "ok")

            processed.add(cat_url)
            print(f"[{spec.name}] {cat_name}: +{cat_added} (всего {len(items)})")

    except StoreAbortedError as e:
        print(f"[{spec.name}] остановлено: {e}")

    return manifest
