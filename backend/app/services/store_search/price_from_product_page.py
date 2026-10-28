"""Довизит на страницу товара ЗА ЦЕНОЙ, когда страница поиска/листинга её не
отдаёт (magazin01.ru, возможно promalper.com при будущих изменениях вёрстки).
Разбор — schema.org Product/Offer (JSON-LD `@type":"Product"` →
`offers.price`, тот же паттерн, что уже проверен живыми фикстурами в
tools/harvest/stores/magazin01.py) + запасной путь `itemprop="price"`
(meta/content или текст) — ОБА пути уже встречались в харвест-сборщиках
разных магазинов (ПРАВИЛО №6 — переиспользуем те же эвристики, не второй
набор регулярок на каждый магазин).

TODO(перенос харвест-парсеров в бэкенд): сборщики tools/harvest/* не попадают
в образ бэкенда (ПРАВИЛО запрета — tools/harvest трогать нельзя, это чужая
сессия), поэтому этот хелпер — НЕЗАВИСИМАЯ копия только эвристики разбора
цены со страницы товара (две строки регэкспа), а не импорт модуля harvest.
Когда харвест-парсеры будут перенесены в backend/ (отдельная задача владельца)
— рассмотреть, можно ли свести на один источник."""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

_LDJSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>([\s\S]*?)</script>', re.IGNORECASE)
_ITEMPROP_PRICE_META_RE = re.compile(r'itemprop="price"[^>]*content="([^"]+)"', re.IGNORECASE)
_ITEMPROP_PRICE_TEXT_RE = re.compile(r'itemprop="price"[^>]*>([^<]+)<', re.IGNORECASE)
_ITEMPROP_IMAGE_RE = re.compile(r'itemprop="image"[^>]*(?:content|src)="([^"]+)"', re.IGNORECASE)


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
