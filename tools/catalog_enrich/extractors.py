"""Извлечение полей со страниц товаров kuvalda.ru, regard.ru и magazin01.ru.

Проверено на реальных страницах 27.10.2026 (см. отчёт):
  - kuvalda.ru: JSON-LD <script type="application/ld+json"> с "@type":"Product"
    содержит "brand":{"name": ...} и "sku" (артикул производителя — у
    "Винтоверт ... SKIL ID6739 solo ID6739SE00" sku="ID6739SE00", отличается
    от номера товара Кувалды в URL/source_id).
  - regard.ru: Next.js страница, <script id="__NEXT_DATA__"> содержит JSON с
    props.initialState.product.data.vendor (бренд), .vendorcode (код/артикул
    производителя) и .characteristics — список групп {"title","data":[
    {"name","value",...}, ...]} с настоящими названиями характеристик.
  - magazin01.ru: тот же JSON-LD @type=Product shape, что у kuvalda.ru —
    extract_kuvalda() ниже переиспользуется для него без изменений (ПРАВИЛО
    №6, не заводим вторую функцию с тем же разбором): "brand":{"name": ...}
    (например "НПО Пульс") и "sku" — у magazin01 sku это 13-значный
    ВНУТРЕННИЙ код магазина (контрольная цифра EAN не сходится — это не
    штрихкод), используется только как store_article, не как артикул
    производителя.
"""
import json
import re
from typing import Optional

LDJSON_RE = re.compile(
    r'application/ld\+json"[^>]*>(.*?)</script>', re.S
)
NEXTDATA_RE = re.compile(
    r'__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)

# Код в скобках в конце названия, похожий на артикул производителя: латиница
# и/или цифры с возможными дефисами, минимум 5 значащих символов.
_TRAILING_CODE_RE = re.compile(r"\(([A-Za-z0-9][A-Za-z0-9\-]{4,})\)\s*$")


def _iter_ldjson_blocks(html: str):
    for m in LDJSON_RE.finditer(html):
        raw = m.group(1).strip()
        # На странице несколько JSON-LD блоков; иногда это JSON-массив.
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            for entry in data:
                yield entry
        else:
            yield data


def extract_kuvalda(html: str) -> dict:
    """Возвращает {"brand": str|None, "sku": str|None} из JSON-LD Product."""
    for entry in _iter_ldjson_blocks(html):
        if not isinstance(entry, dict):
            continue
        if entry.get("@type") != "Product":
            continue
        brand = entry.get("brand")
        brand_name = None
        if isinstance(brand, dict):
            brand_name = brand.get("name")
        elif isinstance(brand, str):
            brand_name = brand
        sku = entry.get("sku")
        if sku is not None:
            sku = str(sku).strip() or None
        return {"brand": (brand_name or "").strip() or None, "sku": sku}
    return {"brand": None, "sku": None}


def extract_regard(html: str) -> dict:
    """Возвращает {"vendor": str|None, "vendorcode": str|None,
    "characteristics": [{"name","value"}, ...]} из __NEXT_DATA__."""
    m = NEXTDATA_RE.search(html)
    if not m:
        return {"vendor": None, "vendorcode": None, "characteristics": []}
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return {"vendor": None, "vendorcode": None, "characteristics": []}

    try:
        product = data["props"]["initialState"]["product"]["data"]
    except (KeyError, TypeError):
        return {"vendor": None, "vendorcode": None, "characteristics": []}

    vendor = product.get("vendor")
    vendorcode = product.get("vendorcode")
    vendor = (vendor or "").strip() or None
    vendorcode = (str(vendorcode).strip() if vendorcode else None) or None

    characteristics: list[dict] = []
    seen_names: set[str] = set()
    for group in product.get("characteristics") or []:
        for row in (group or {}).get("data") or []:
            name = (row.get("name") or "").strip()
            value = row.get("value")
            if not name or value is None:
                continue
            value_str = str(value).strip()
            if not value_str:
                continue
            key = name.lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            characteristics.append({"name": name, "value": value_str, "unit": None})

    return {"vendor": vendor, "vendorcode": vendorcode, "characteristics": characteristics}


def trailing_code_from_name(name: str) -> Optional[str]:
    """«(9S6-B0A431-1054)» на конце названия товара — похоже на артикул
    производителя (latin/digits/дефисы, ≥5 знаков)."""
    if not name:
        return None
    m = _TRAILING_CODE_RE.search(name.strip())
    if not m:
        return None
    return m.group(1)
