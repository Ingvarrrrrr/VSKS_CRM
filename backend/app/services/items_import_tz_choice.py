"""Своё ТЗ позиции при импорте (владелец, 14.10.2026, план
item-tz-description.md) — выбор каталог/файл по строке + ОДИН матчер
товара каталога, общий для preview (показывает catalog_description рядом с
description из файла) и для confirm/save (решает, что писать в
PurchaseItem.tz_description). ПРАВИЛО №6: раньше exact+fuzzy матчинг был
инлайн-дублирован в items_import_catalog.py::_save_smart_preview_to_purchase
и в purchase_items_import_mapped.py::import_items_mapped — теперь оба места
зовут match_catalog_product отсюда, а preview-ветки (которые раньше матчинг
вообще не делали для pid-эндпоинтов) используют ту же функцию, чтобы
"каталожное описание" в окне сравнения было ровно тем товаром, который потом
и сматчится при сохранении.

ПРАВИЛО №5: новая логика — отдельный файл (не дописано в items_import_catalog.py
или в роутеры).
"""
from typing import Optional

from app.models.product import Product
from app.services.product_catalog_match import normalize_product_name
from app.services.product_matcher import score as _fuzzy_score, SCORE_AUTO as _SCORE_AUTO


def match_catalog_product(item_name: str, product_by_name: dict) -> Optional[Product]:
    """Найти товар каталога для строки импорта: 1) точное совпадение по
    normalize_product_name (fast path), 2) fuzzy-фоллбэк (лучший кандидат
    выше SCORE_AUTO). `product_by_name` — словарь normalize_product_name(name)
    → Product, построенный index_products_by_name/find_products_by_normalized_names
    (Правило №6 — тот же словарь, что и везде в импорте позиций)."""
    if not item_name:
        return None
    matched = product_by_name.get(normalize_product_name(item_name))
    if matched:
        return matched
    best_score = 0.0
    best_candidate: Optional[Product] = None
    for _key, _p in product_by_name.items():
        _s = _fuzzy_score(item_name, _p.name if hasattr(_p, "name") else _key)
        if _s > best_score:
            best_score = _s
            best_candidate = _p
    if best_score >= _SCORE_AUTO and best_candidate is not None:
        return best_candidate
    return None


def resolve_tz_description(
    file_description: Optional[str],
    row_num,
    tz_choices: Optional[dict],
) -> Optional[str]:
    """Решает, какой текст писать в tz_description позиции по строке импорта.

    tz_choices: {"<row_num>": "catalog"|"file"} — выбор владельца в окне
    сравнения (ItemTzCompareDialog.vue). "catalog" → NULL (позиция покажет
    действующее ТЗ каталога через item_tz.py, Правило №6 — один хелпер
    "действующее ТЗ позиции"). Любое другое значение/отсутствие строки в
    словаре → текст из файла (владелец, 14.10.2026: «по умолчанию — из
    файла»)."""
    choice = (tz_choices or {}).get(str(row_num)) if row_num is not None else None
    if choice == "catalog":
        return None
    return file_description
