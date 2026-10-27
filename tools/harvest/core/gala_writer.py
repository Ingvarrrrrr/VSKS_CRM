"""Сборка item формата gala-catalog СТРОГО без значений по умолчанию
(ПРАВИЛО №5/№6) — единственное место в tools/harvest, решающее каким должен
быть manufacturer/seller_inn/форма item. Store-модули (stores/*.py) вызывают
только эти функции, item вручную не собирают. Нет данных → null/[] — никогда
"Производитель"/тип товара/страна "Россия" по умолчанию (брак старых
сборщиков из C:\\Users\\1\\.gemini\\antigravity-ide\\scratch\\, не повторять)."""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from tools.harvest.core.gala_contracts import load_gala_contracts

_CONTRACTS = load_gala_contracts()


def _brand_dictionary_module():
    """Импорт (НЕ копия, ПРАВИЛО №6) tools/catalog_enrich/brand_dictionary.py
    — та же BrandDictionary/целословный поиск бренда в тексте, что
    используется для дозаполнения Кувалды (stores/kuvalda.py). Сам модуль
    не тянет backend/app (только json/re/pathlib) — тяжёлый
    fold_brand_or_code (app.services.brand_code_fold) сознательно НЕ
    используется здесь: он транзитивно требует app.models.product +
    SQLAlchemy, то есть БД-слой, которого у tools/harvest по конструкции
    нет (gala_contracts.py существует именно для того, чтобы его не тянуть).
    Поэтому find_brand_in_name() ниже передаёт в BrandDictionary лёгкий
    quality-шим: is_bogus_manufacturer — настоящий (из gala_contracts),
    fold_brand_or_code — упрощённый (регистр/пробелы, без свёртки
    гомоглифов кириллица/латиница) — осознанное отличие от полного
    fold_brand_or_code, не брак."""
    import importlib
    return importlib.import_module("tools.catalog_enrich.brand_dictionary")


class _LightFoldQuality:
    """Квалити-шим для BrandDictionary (см. _brand_dictionary_module) — тот
    же интерфейс (fold_brand_or_code/is_bogus_manufacturer), что ждёт
    tools/catalog_enrich/brand_dictionary.py, без тяги backend БД-слоя."""

    def fold_brand_or_code(self, text) -> str:
        if not text:
            return ""
        return " ".join(str(text).strip().lower().split())

    def is_bogus_manufacturer(self, manufacturer, name=None) -> bool:
        return _CONTRACTS.is_bogus_manufacturer(manufacturer, name)


def find_brand_in_name(name: str, known_brands: set[str]) -> Optional[str]:
    """Ищет известный бренд (seed ∪ known_brands, собранные в этом прогоне)
    целым словом прямо в названии товара — ТЕМ ЖЕ алгоритмом/классом, что
    tools/catalog_enrich/brand_dictionary.BrandDictionary (владелец,
    27.10.2026: "у 842 из 843 товаров Кувалды бренд со страницы и так стоит
    в названии" — для магазинов без бренда/характеристик в разделе этого
    достаточно, чтобы НЕ открывать страницу товара вообще)."""
    mod = _brand_dictionary_module()
    quality = _LightFoldQuality()
    d = mod.BrandDictionary(quality)
    for brand in KNOWN_BRANDS_SEED | {b for b in known_brands or set()}:
        d.add(brand)
    d.finalize()
    return d.find_in_name(name)

# Ручное дополнение словаря известных брендов (владелец: держать ТОЛЬКО тут,
# не плодить по store-модулям) — явные бренды, которые могут не встретиться
# среди уже собранных "хороших" строк текущего прогона.
KNOWN_BRANDS_SEED: set[str] = {
    "makita", "bosch", "dewalt", "intel", "amd", "asus", "msi", "gigabyte",
    "kingston", "corsair", "samsung", "seagate", "western digital", "hp",
    "lenovo", "dell", "acer", "epson", "canon", "brother", "netac",
}

_BRAND_CHARACTERISTIC_NAMES = {"бренд", "производитель", "торговая марка"}


def known_brands_from_items(items: list[dict]) -> set[str]:
    """Множество manufacturer (в нижнем регистре), прошедших
    is_bogus_manufacturer()==False среди уже собранных в текущем прогоне
    строк — доп. словарь брендов для resolve_manufacturer() следующих строк
    того же магазина."""
    brands: set[str] = set()
    for item in items:
        manufacturer = item.get("manufacturer")
        if manufacturer and not _CONTRACTS.is_bogus_manufacturer(manufacturer, item.get("name")):
            brands.add(manufacturer.strip().lower())
    return brands


def _clean_brand(value) -> Optional[str]:
    if isinstance(value, dict):
        value = value.get("name")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def resolve_manufacturer(
    name: str,
    jsonld_brand,
    characteristics: list[dict],
    known_brands: set[str],
) -> Optional[str]:
    """Порядок приоритета:
      1) JSON-LD brand (строка или {"name": ...}), очищенный и непустой;
      2) характеристика с name в {"Бренд","Производитель","Торговая марка"}
         (без учёта регистра) — её value;
      3) явное совпадение известного бренда (seed ∪ known_brands) как
         отдельного слова в name (без учёта регистра).
    Результат, отбракованный is_bogus_manufacturer(), не возвращается (None)."""
    candidate = _clean_brand(jsonld_brand)

    if not candidate:
        for c in characteristics or []:
            c_name = (c.get("name") or "").strip().lower()
            if c_name in _BRAND_CHARACTERISTIC_NAMES:
                value = (c.get("value") or "").strip()
                if value:
                    candidate = value
                    break

    if not candidate:
        all_known = KNOWN_BRANDS_SEED | {b.lower() for b in known_brands}
        tokens = [t.strip(".,()").lower() for t in (name or "").split()]
        for token in tokens:
            if token in all_known:
                candidate = token
                break

    if not candidate:
        return None
    if _CONTRACTS.is_bogus_manufacturer(candidate, name):
        return None
    return candidate


def seller_inn_for(url: Optional[str]) -> Optional[str]:
    """Обёртка над gala_contracts/stores.seller_inn_for_url — никакого
    собственного ИНН в tools/harvest (ПРАВИЛО №6)."""
    return _CONTRACTS.seller_inn_for_url(url)


def build_manifest(source: str, source_file: str) -> dict:
    return {
        "format": _CONTRACTS.GALA_FORMAT_NAME,
        "version": _CONTRACTS.GALA_FORMAT_VERSION,
        "source": source,
        "source_file": source_file,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "items": [],
        "excluded": [],
    }


def build_item(
    *,
    name: str,
    category: Optional[str] = None,
    category_path: Optional[list] = None,
    product_type: Optional[str] = None,
    unit: Optional[str] = None,
    price: Optional[float] = None,
    price_date: Optional[str] = None,
    currency: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturer_article: Optional[str] = None,
    store_article: Optional[str] = None,
    description: Optional[str] = None,
    characteristics: Optional[list] = None,
    photos: Optional[list] = None,
    links: Optional[list] = None,
    source_url: Optional[str] = None,
    source_id: Optional[str] = None,
    country_origin: Optional[str] = None,
    barcodes: Optional[list] = None,
    seller_inn: Optional[str] = None,
) -> dict:
    """Собирает item по контракту format.py. Отсутствующие данные — None/[]
    (никогда значение-по-умолчанию)."""
    return {
        "name": name,
        "category": category,
        "category_path": category_path or [],
        "product_type": product_type,
        "unit": unit,
        "price": price,
        "price_date": price_date,
        "currency": currency,
        "manufacturer": manufacturer,
        "manufacturer_article": manufacturer_article,
        "store_article": store_article,
        "description": description,
        "characteristics": characteristics or [],
        "photos": photos or [],
        "links": links or [],
        "source_url": source_url,
        "source_id": source_id,
        "country_origin": country_origin,
        "barcodes": barcodes or [],
        "seller_inn": seller_inn,
    }
