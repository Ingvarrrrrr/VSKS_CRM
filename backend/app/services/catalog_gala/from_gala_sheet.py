"""Конвертер внутренней таблицы ГАЛА (catalog_goods_*.json) → формат GALA (format.py).

Вход (raw) — ЛИБО list[dict] (как catalog_goods_1010.json: {row, name,
description, category, kind, unit, pkg_qty, pkg_unit, price,
price_date "ДД.ММ.ГГГГ", link_1..3/price_1..3, photo_url, is_reusable
"да"/"нет", is_active "да"/"нет", feo_category}), ЛИБО dict, сгруппированный
по категориям (как catalog_by_categories.json: {категория: [строки той же
формы]}) — если dict, все списки разворачиваются (flatten) в один в порядке
ключей словаря.

Проверено на реальных файлах (26.10): catalog_by_categories.json содержит
РОВНО те же 1008 строк, что и catalog_goods_1010.json — то же множество
(row, name), просто перегруппированное по полю category. Второй файл не несёт
новых данных, это представление первого.

Правила отображения полей:
  - feo_category из исходника НЕ переносится в GALA (явно оговорено владельцем
    — это не однозначный экспорт одного поля в другое, категория ФЭО и
    категория каталога — разные классификации).
  - category: "Не указано" (без учёта регистра/пробелов) → null, иначе как есть.
  - kind → product_type; item_kind = "товар" (kind здесь — бытовое название
    вида товара из таблицы ГАЛА, а не 44fz item_kind «товар/услуга/работа»).
  - price_date "ДД.ММ.ГГГГ" → "YYYY-MM-DD"; пусто/невалидно → null.
  - is_reusable/is_active: "да"→true, "нет"→false (регистр не важен), иначе null.
  - link_1/price_1, link_2/price_2, link_3/price_3 (пустые игнорируются) →
    links=[{"url","price"}, ...]; source_url = link_1, если есть.
  - photo_url → photos=[photo_url], если непусто.
  - pkg_qty/pkg_unit → pack_quantity/pack_unit.
  - row → source_id = str(row).
  - description переносится как текст поставщика (description в GALA).
  - name/description чистятся через catalog_gala.clean.clean_text (ПРАВИЛО
    №6, HTML-сущности/<br>/теги — на случай, если внутренняя таблица ГАЛА
    когда-то содержала скопированный HTML-текст).
"""
import re
from datetime import datetime

from app.services.catalog_gala.clean import clean_text

_NOT_SPECIFIED_RE = re.compile(r"^\s*не\s+указано\s*$", re.IGNORECASE)


def _normalize_category(value):
    if not value or _NOT_SPECIFIED_RE.match(value):
        return None
    return value


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def _parse_bool(value):
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v == "да":
        return True
    if v == "нет":
        return False
    return None


def _parse_number(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _flatten(raw):
    if isinstance(raw, dict):
        rows = []
        for category_rows in raw.values():
            rows.extend(category_rows or [])
        return rows
    return list(raw or [])


def _convert_row(row: dict) -> dict:
    category = _normalize_category(row.get("category"))

    links = []
    for i in (1, 2, 3):
        url = row.get(f"link_{i}")
        if url:
            links.append({"url": url, "price": _parse_number(row.get(f"price_{i}"))})
    source_url = row.get("link_1") or None

    photo_url = row.get("photo_url") or None
    price = _parse_number(row.get("price"))
    if price == 0:
        price = None

    return {
        "name": clean_text(row.get("name")),
        "category": category,
        "category_path": [category] if category else [],
        "product_type": row.get("kind") or None,
        "item_kind": "товар",
        "unit": row.get("unit") or None,
        "pack_quantity": row.get("pkg_qty"),
        "pack_unit": row.get("pkg_unit") or None,
        "price": price,
        "price_date": _parse_date(row.get("price_date")),
        "currency": "RUB" if price is not None else None,
        "manufacturer": None,
        "article": None,
        "description": clean_text(row.get("description")),
        "characteristics": [],
        "photos": [photo_url] if photo_url else [],
        "links": links,
        "source_url": source_url,
        "source_id": str(row["row"]) if row.get("row") is not None else None,
        "is_reusable": _parse_bool(row.get("is_reusable")),
        "is_active": _parse_bool(row.get("is_active")),
    }


def convert(raw, source_file: str) -> dict:
    rows = _flatten(raw)
    items = [_convert_row(row) for row in rows]
    return {"source": "gala_sheet", "items": items}
