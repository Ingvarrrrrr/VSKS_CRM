"""Разбор страницы товара medtehno.ru — перенесено из
tools/harvest/stores/medtehno.py (ПРАВИЛО №6, единственный источник этой
логики). Нет JSON-LD — microdata itemprop= (price/image) + HTML-таблица
характеристик `<tr><td>Имя</td><td>Значение</td></tr>`."""
from __future__ import annotations

import html as _html
import re

_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL)
_PRICE_RE = re.compile(r'itemprop="price"[^>]*>([\d.]+)</span>')
_IMAGE_RE = re.compile(r'itemprop="image"[^>]*content="([^"]+)"')
_SPEC_ROW_RE = re.compile(
    r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>", re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    text = _TAG_RE.sub(" ", text)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_product_page(html: str, url: str) -> dict:
    h1 = _H1_RE.search(html)
    name = _clean(h1.group(1)) if h1 else None

    price_m = _PRICE_RE.search(html)
    price = float(price_m.group(1)) if price_m else None

    image_m = _IMAGE_RE.search(html)
    image = image_m.group(1) if image_m else None

    characteristics = []
    for raw_name, raw_value in _SPEC_ROW_RE.findall(html):
        name_clean = _clean(raw_name).rstrip(":").strip()
        value_clean = _clean(raw_value).strip()
        if name_clean and value_clean and len(name_clean) < 80:
            characteristics.append({"name": name_clean, "value": value_clean, "unit": None, "in_description": False})

    return {
        "name": name,
        "price": price,
        "photos": [image] if image else [],
        "characteristics": characteristics,
    }
