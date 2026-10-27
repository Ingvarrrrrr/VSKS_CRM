"""Общий хелпер для template.py (формат ХО, 3 уровня ФЭО в отдельных
колонках) и template_stages.py (лист GoodsService, 4 уровня ФЭО) —
plan_catalog.load_plan_catalog() → (имя плановой позиции, уровни пути) для
одной строки шаблона. ПРАВИЛО №6 — один разбор записи каталога на строку
шаблона, не по копии в каждом файле-генераторе.
"""
from __future__ import annotations

from typing import Optional


def entry_name_and_levels(entry: dict, depth: int) -> tuple[Optional[str], list]:
    """entry — элемент plan_catalog (path/'name'/kind, см. plan_catalog.py).

    Возвращает (имя плановой позиции шаблона|None, [уровень]*depth — ПОСЛЕДНИЕ
    depth частей пути ФЭО, считая саму категорию её последним уровнем, если
    строка каталога — лист дерева без своей FeoPlannedItem, см. docstring
    load_plan_catalog: «плановая позиция» в шаблоне тогда — сама категория,
    плюс path_parts дополнен её именем)."""
    path_parts = [p for p in (entry.get("path") or "").split(" › ") if p]
    if entry.get("kind") == "planned_item":
        plan_item_name = entry.get("name")
    else:
        path_parts = (path_parts + [entry.get("name")]) if path_parts else [entry.get("name")]
        plan_item_name = None
    levels = ([None] * depth + path_parts)[-depth:]
    return plan_item_name, levels
