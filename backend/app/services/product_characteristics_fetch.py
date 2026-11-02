"""Получение характеристик напрямую со страницы товара по URL магазина
(владелец: «Кнопка "Вставить с сайта" для меня предполагает, что парсер сам
заберёт данные с сайта»).

ПРАВИЛО №6: переиспользует существующие store_pages-парсеры
(app.services.store_pages) и общий JSON-LD/HTML парсер
(app.services.store_search.price_from_product_page.extract_product_details),
а также нормализатор разделения единиц _separate_unit
(app.services.product_characteristics_parse).
"""
from __future__ import annotations

import html as _html
import re
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from app.services.catalog_gala.clean import clean_text
from app.services.catalog_gala.stores import STORES
from app.services.product_characteristics_parse import _separate_unit
from app.services.store_pages import get_parser, product_page_fetch_url
from app.services.store_search.price_from_product_page import extract_product_details
from app.services.store_search.registry import ADAPTERS
from app.utils.safe_url import UnsafeUrlError, assert_safe_url

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

_TABLE_ROW_RE = re.compile(
    r"<tr[^>]*>\s*<t[dh][^>]*>(.*?)</t[dh]>\s*<t[dh][^>]*>(.*?)</t[dh]>\s*</tr>",
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(s: Any) -> str:
    if s is None:
        return ""
    text = _TAG_RE.sub(" ", str(s))
    text = _html.unescape(text)
    return clean_text(text)


def _detect_store_key(url: str) -> Optional[str]:
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return None

    # 1. Match against ADAPTERS
    for key, adapter in ADAPTERS.items():
        domain = (getattr(adapter, "domain", None) or "").lower()
        if domain and (host == domain or host.endswith("." + domain)):
            return key

    # 2. Match against STORES
    for known_domain in STORES:
        kd = known_domain.lower()
        if host == kd or host.endswith("." + kd):
            candidate = kd.split(".")[0].replace("-", "_")
            return candidate

    return None


async def fetch_characteristics_from_url(url: str) -> list[dict]:
    """Скачивает страницу по url, извлекает характеристики через store_pages
    или generic JSON-LD/HTML, и строго разделяет числовые значения и единицы
    измерения (value и unit)."""
    clean_url = (url or "").strip()
    if not clean_url:
        raise HTTPException(status_code=400, detail="Укажите ссылку на страницу товара")

    try:
        assert_safe_url(clean_url)
    except UnsafeUrlError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Недопустимая ссылка: {e}") from e

    store_key = _detect_store_key(clean_url)
    fetch_url = product_page_fetch_url(store_key, clean_url) if store_key else clean_url
    if fetch_url != clean_url:
        try:
            assert_safe_url(fetch_url)
        except UnsafeUrlError as e:
            raise HTTPException(status_code=400, detail=e.message) from e

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(fetch_url, headers=DEFAULT_HEADERS)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Не удалось подключиться к сайту: {e}",
        ) from e

    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Не удалось загрузить страницу (статус {resp.status_code})",
        )

    parser = get_parser(store_key) if store_key else None
    raw_chars: list[dict] = []

    if parser is not None:
        try:
            parsed = parser(resp.text, clean_url) or {}
            raw_chars = parsed.get("characteristics") or []
        except Exception:
            raw_chars = []
    else:
        try:
            generic = extract_product_details(resp.text)
            raw_chars = generic.get("characteristics") or []
        except Exception:
            raw_chars = []

    if not raw_chars:
        for m in _TABLE_ROW_RE.finditer(resp.text or ""):
            n_raw, v_raw = m.group(1), m.group(2)
            if "<tr" in n_raw.lower() or "<tr" in v_raw.lower():
                continue
            name = _clean_text(n_raw).rstrip(":").strip()
            val = _clean_text(v_raw).strip()
            if name and val and len(name) <= 200 and len(val) <= 2000:
                if name.lower() in ("параметр", "характеристика", "свойство", "название", "имя"):
                    continue
                raw_chars.append({"name": name, "value": val, "unit": None})

    out: list[dict] = []
    seen: set[str] = set()
    for char in raw_chars:
        if not isinstance(char, dict):
            continue
        name = _clean_text(char.get("name"))
        value = _clean_text(char.get("value"))
        unit = char.get("unit")
        if not unit:
            val_part, unit_part = _separate_unit(value)
            value = _clean_text(val_part)
            unit = _clean_text(unit_part) or None
        else:
            unit = _clean_text(unit) or None

        if not name or not value:
            continue

        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        out.append({
            "name": name,
            "value": value,
            "unit": unit,
            "in_description": True,
        })

    return out
