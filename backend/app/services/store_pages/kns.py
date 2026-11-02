"""Разбор ПОДСТРАНИЦЫ характеристик kns.ru (`<product_url>characteristics/`)
— перенесено из tools/harvest/stores/kns.py (ПРАВИЛО №6, единственный
источник этой логики). Пары `field-ex-name` / `word-break-all`.
"PN" → артикул производителя, "Производитель" → бренд (запасной источник,
если GA4-данные раздела их не дали)."""
from __future__ import annotations

import re

_CHAR_ROW_RE = re.compile(
    r'field-ex-name"[^>]*>\s*([^<]+?)\s*</div>\s*<div class="[^"]*word-break-all"[^>]*>(.*?)</div>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


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
