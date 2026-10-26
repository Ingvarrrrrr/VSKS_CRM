"""Формат GALA — единый промежуточный JSON-формат каталога товаров (владелец,
26.10), в который конвертируются разные выгрузки поставщиков перед загрузкой в
products (загрузчик в products придёт отдельным шагом).

Подпакеты:
  - format.py          — константы формата + validate_gala_catalog()
  - clean.py           — clean_text(), единая очистка HTML-мусора (ПРАВИЛО №6)
  - electro_consistency.py — проверка «N×S» в названии кабеля против характеристик
  - from_electro_mpo.py — конвертер выгрузки electro-mpo.ru
  - from_vkusvill.py    — конвертер выгрузки vkusvill.ru (плоский и структурный варианты)
  - from_gala_sheet.py  — конвертер внутренней таблицы ГАЛА (catalog_goods_*.json)
  - from_baucenter.py   — конвертер выгрузки baucenter.ru

См. backend/scripts/catalog_to_gala.py — CLI, который вызывает эти convert().
"""
from .format import GALA_FORMAT_NAME, GALA_FORMAT_VERSION, validate_gala_catalog

__all__ = ["GALA_FORMAT_NAME", "GALA_FORMAT_VERSION", "validate_gala_catalog"]
