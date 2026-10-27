"""Словарь брендов для поиска производителя ПРЯМО В НАЗВАНИИ товара Кувалды —
до похода на страницу (владелец, 27.10.2026, решение по итогам 843
полученных страниц: у 842 из 843 бренд со страницы и так стоит в названии).

Источники словаря (один словарь, одна функция — ПРАВИЛО №6, не плодить
вторую "угадайку бренда"):
  1. kuvalda-кэш (data.brand) — бренды, УЖЕ подтверждённые страницей Кувалды
     в этом же прогоне.
  2. category_path файла Кувалды — лист пути, когда он написан латиницей
     (сами категории типа "Электроинструмент / Makita"); кириллические листья
     в этом файле — сплошь названия типов товара ("Перфораторы", "Дрели" и
     т.п.), не бренды, поэтому НЕ берутся (та же логика, что у
     manufacturer_quality.is_bogus_manufacturer: латиница не проверяется
     правилом "совпадает с типом товара", потому что реальные бренды почти
     всегда латиница).
  3. manufacturer из ДРУГИХ выгрузок "Товары и ТЗ" (kns_computers_office_
     equipment.json, baucenter_construction_all.json, baucenter_electro_
     lighting.json, baucenter_tools_hardware.json — electro_mpo в этой папке
     отдельным файлом не найден, в словарь не попадает) — только строки, где
     manufacturer НЕ is_bogus_manufacturer(...).

Поиск в названии — целым словом (границы: не буква/цифра кириллица/
латиница), через fold_brand_or_code (гомоглифы/регистр схлопнуты — бренд
найдётся независимо от того, латиницей или кириллицей он напечатан и там,
и там). При нескольких совпадениях — самое длинное.
"""
import json
import re
from pathlib import Path
from typing import Optional

_LATIN_RE = re.compile(r"[A-Za-z]")
_WORD_BOUNDARY_CHARS = r"a-zа-яё0-9"

OTHER_CATALOG_FILES = (
    "kns_computers_office_equipment.json",
    "baucenter_construction_all.json",
    "baucenter_electro_lighting.json",
    "baucenter_tools_hardware.json",
)


class BrandDictionary:
    def __init__(self, quality):
        self._quality = quality
        # fold_key -> каноническое написание (первое встреченное)
        self._entries: dict[str, str] = {}
        # fold_key -> скомпилированный целословный regex (строится лениво)
        self._patterns: list[tuple[str, re.Pattern]] = []

    def add(self, brand: str) -> None:
        brand = (brand or "").strip()
        if not brand:
            return
        key = self._quality.fold_brand_or_code(brand)
        if not key:
            return
        if key not in self._entries:
            self._entries[key] = brand

    def finalize(self) -> None:
        # Длинные ключи — первыми, чтобы при пересечении выигрывало самое
        # длинное совпадение.
        self._patterns = [
            (key, re.compile(
                rf"(?<![{_WORD_BOUNDARY_CHARS}]){re.escape(key)}(?![{_WORD_BOUNDARY_CHARS}])",
                re.IGNORECASE,
            ))
            for key in sorted(self._entries, key=len, reverse=True)
        ]

    def __len__(self) -> int:
        return len(self._entries)

    def find_in_name(self, name: str) -> Optional[str]:
        """Возвращает каноническое написание бренда, найденного целым словом
        в name (после фолда), или None. Самое длинное совпадение побеждает
        (self._patterns уже отсортирован по длине ключа по убыванию)."""
        if not name:
            return None
        folded_name = self._quality.fold_brand_or_code(name)
        if not folded_name:
            return None
        for key, pattern in self._patterns:
            if pattern.search(folded_name):
                canonical = self._entries[key]
                if not self._quality.is_bogus_manufacturer(canonical, name):
                    return canonical
        return None


def _load_items(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data.get("items") or []


def build_kuvalda_brand_dictionary(quality, kuvalda_cache_path: Path, kuvalda_items: list,
                                    other_catalogs_dir: Path) -> BrandDictionary:
    d = BrandDictionary(quality)

    # 1) kuvalda-кэш — бренды, уже подтверждённые страницами в этом прогоне.
    if kuvalda_cache_path.exists():
        with kuvalda_cache_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not rec.get("ok"):
                    continue
                brand = (rec.get("data") or {}).get("brand")
                if brand:
                    d.add(brand)

    # 2) category_path файла Кувалды — только латиница в листе.
    for item in kuvalda_items:
        cp = item.get("category_path") or []
        if not cp:
            continue
        leaf = cp[-1]
        if leaf and _LATIN_RE.search(leaf):
            d.add(leaf)

    # 3) manufacturer из других выгрузок "Товары и ТЗ" (только не-bogus).
    for fname in OTHER_CATALOG_FILES:
        path = other_catalogs_dir / fname
        if not path.exists():
            continue
        for item in _load_items(path):
            manufacturer = item.get("manufacturer")
            if not manufacturer:
                continue
            if quality.is_bogus_manufacturer(manufacturer, item.get("name")):
                continue
            d.add(manufacturer)

    d.finalize()
    return d
