"""Разбор страницы товара safe.ru (завод ПРОМЕТ) — перенесено из
tools/harvest/stores/safe.py (ПРАВИЛО №6, единственный источник этой
логики). tools/harvest/stores/safe.py загружает parse_product_page отсюда
через _backend_bridge; store_search/take.py — для довизита после «Взять».

Bitrix-шаблон: `<meta itemprop="price" content="4750">`, характеристики —
`<div class="card__characteristics"><table id="table1"><tr><td>Имя:</td>
<td>Значение</td></tr>` (строки "Производитель"/"Страна" прямо в таблице).
store_article — `data-id="<id>"` на кнопке "В список покупок" (внутренний
ID Bitrix, не артикул производителя — того поля на странице нет).
Подробности — см. историю tools/harvest/stores/safe.py (git log)."""
from __future__ import annotations

import re

_H1_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>")
_PRICE_RE = re.compile(r'itemprop="price"\s+content="([\d.]+)"')
_DATA_ID_RE = re.compile(r'data-id="(\d+)"')
_TABLE_RE = re.compile(r'id="table1">([\s\S]*?)</table>')
_ROW_RE = re.compile(r"<td>([^<]+)</td>\s*<td>([^<]*)</td>")


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
