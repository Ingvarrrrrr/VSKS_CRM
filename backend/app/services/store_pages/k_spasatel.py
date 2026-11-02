"""Разбор страницы товара k-spasatel.ru — перенесено из
tools/harvest/stores/k_spasatel.py (ПРАВИЛО №6, единственный источник этой
логики). Нет JSON-LD (Opencart-подобный шаблон): `js-product-code` —
артикул САМОГО k-spasatel (НЕ производителя); характеристики — пары внутри
id="tab-description" в двух форматах разметки (`<p>Имя:&nbsp;Значение</p>`
и `<table><tr><td>Имя</td><td>Значение</td></tr></table>`)."""
from __future__ import annotations

import re

BASE_URL = "https://k-spasatel.ru"

_H1_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>")
_PRODUCT_CODE_RE = re.compile(r'js-product-code">([^<]+)<')
_IMG_RE = re.compile(r'<img[^>]+src="([^"]*catalog/[^"]+\.(?:jpg|jpeg|png|webp))"', re.I)
_PRICE_VALUE_RE = re.compile(r'itemprop="price"[^>]*content="([\d.]+)"')
_SPEC_P_RE = re.compile(r"<p>\s*([^<:]{2,60}?):&nbsp;([^<]{1,150})</p>")
_SPEC_TABLE_ROW_RE = re.compile(
    r"<tr>\s*<td>([^<]{2,60})</td>\s*<td>([^<]{1,150})</td>\s*</tr>", re.DOTALL
)


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
