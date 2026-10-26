"""Конвертер общего формата выгрузок трёх магазинов (promalp_height_safety_
nomenclature.json, rescue_medical_nomenclature.json, fire_equipment_
nomenclature.json) → формат GALA (см. format.py). Владелец, 2026-10-26,
Задача 1.

Вход (raw) — список объектов вида:
  {name, category, unit, price_rub, source_store, link_1, photo_url,
   description, specifications: {"<ключ>": "<значение>", ...}}

Правила отображения полей:
  - name чистится через catalog_gala.clean.clean_text.
  - category → category как есть; product_type НЕ задаётся (владелец:
    у этих трёх выгрузок категория и так достаточно конкретна, второй
    уровень не нужен); category_path=[category], если category есть.
  - unit → unit как есть.
  - price_rub: null/0 → None (как у остальных конвертеров).
  - source_store → characteristic "Магазин-источник" (in_description=False —
    это данные о логистике, не о товаре), НЕ в manufacturer (это не
    производитель, а магазин, у которого выгрузка).
  - link_1 → source_url и links=[{"url","price"}], если непусто.
  - photo_url → photos=[photo_url], если непусто.
  - description НЕ переносится (SEO-реклама магазина, решение владельца).
  - specifications → characteristics, с чисткой (_clean_characteristics):
      * ключ ПОСЛЕ clean_text, с обрезанным хвостовым ":" (двоеточие в конце
        ключа — артефакт выгрузки, не часть имени).
      * выбрасываем характеристику целиком, если после чистки:
          - ключ пуст;
          - ключ состоит только из цифр/пробелов/"№";
          - ключ или значение — заглушка вида "#...#" (fire_equipment:
            "#PROP_TITLE#": "#PROP_VALUE#");
          - значение пусто после clean_text;
          - значение длиннее 300 символов (кусок разобранной таблицы
            размеров у части rescue_medical-позиций, см. тест).
      * "Артикул" → article (не дублируется в characteristics).
      * "Производитель"/"Бренд" → manufacturer: "Производитель" имеет
        приоритет; если оба заданы и совпадают (без учёта регистра/
        пробелов) — "Бренд" не дублируется, иначе остаётся обычной
        характеристикой со своим именем.
      * остальные ключи — через spec_parse.split_key_unit (единица после
        запятой в конце ключа, "Диаметр, мм" → name "Диаметр", unit "мм" —
        тот же разбор, что у electro_mpo/baucenter, ПРАВИЛО №6).
      * rescue_medical (определяется по source_file, т.к. все три выгрузки
        идут через один конвертер): "Длина"/"Ширина"/"Высота"/"Вес" БЕЗ
        уточнения — габариты/вес упаковки магазина, не самого товара (у
        самого товара везде более точные ключи типа "Ширина сиденья",
        "Длина ленты") → in_description=False. Значения вида "2.9 кг"
        (единица внутри значения, не ключа) оставляются как есть — это
        value, split_key_unit его не касается.
  - item_kind = "товар". is_reusable/is_active/manufacturer(без спецификации)/
    article/pack_quantity/pack_unit/price_date/source_id — не определены в
    исходнике → None.
"""
import re

from app.services.catalog_gala.clean import clean_text
from app.services.catalog_gala.spec_parse import split_key_unit

_PURE_DIGIT_RE = re.compile(r"^[\d\s№]+$")
_STUB_RE = re.compile(r"^#.+#$")

# Владелец, 2026-10-26: в rescue_medical эти ключи без уточнения — габариты/
# вес упаковки магазина, не самого товара (см. докстринг модуля).
_PACKAGE_DIM_NAMES = {"длина", "ширина", "высота", "вес"}


def _is_rescue_medical(source_file: str) -> bool:
    return "rescue_medical" in (source_file or "").lower()


def _clean_characteristics(specs: dict, is_rescue_medical: bool) -> tuple:
    """Возвращает (characteristics, manufacturer, article)."""
    characteristics = []
    article = None

    # Предварительный проход — найти manufacturer-кандидата из "Производитель"
    # (он главнее "Бренда" независимо от порядка ключей в исходнике).
    manufacturer = None
    for raw_key, raw_value in (specs or {}).items():
        key = clean_text(raw_key)
        if key and key.rstrip(":").strip().lower() == "производитель":
            manufacturer = clean_text(raw_value)
            break

    for raw_key, raw_value in (specs or {}).items():
        key = clean_text(raw_key)
        if not key:
            continue
        key = key.rstrip(":").strip()
        if not key:
            continue
        if _PURE_DIGIT_RE.match(key) or _STUB_RE.match(key):
            continue

        value = clean_text(raw_value)
        if not value:
            continue
        if len(value) > 300:
            continue
        if _STUB_RE.match(value):
            continue

        key_lower = key.lower()

        if key_lower == "артикул":
            article = value
            continue

        if key_lower == "производитель":
            continue  # уже взят в предварительном проходе

        if key_lower == "бренд":
            if manufacturer and manufacturer.strip().lower() == value.strip().lower():
                continue  # дубль "Производителя" — не повторяем
            if manufacturer is None:
                manufacturer = value
                continue
            # отличается от "Производителя" — остаётся обычной характеристикой
            characteristics.append({"name": key, "value": value, "unit": None})
            continue

        name, unit = split_key_unit(key)
        c = {"name": name, "value": value, "unit": unit}
        if is_rescue_medical and name.lower() in _PACKAGE_DIM_NAMES:
            c["in_description"] = False
        characteristics.append(c)

    return characteristics, manufacturer, article


def convert(raw: list, source_file: str) -> dict:
    is_rescue_medical = _is_rescue_medical(source_file)
    items = []
    for row in raw or []:
        price = row.get("price_rub") or None
        if price == 0:
            price = None

        category = row.get("category") or None

        characteristics, manufacturer, article = _clean_characteristics(
            row.get("specifications") or {}, is_rescue_medical
        )

        store = clean_text(row.get("source_store"))
        if store:
            characteristics.append({
                "name": "Магазин-источник", "value": store, "unit": None, "in_description": False,
            })

        url = row.get("link_1") or None
        links = [{"url": url, "price": price}] if url else []

        photo = row.get("photo_url") or None
        photos = [photo] if photo else []

        items.append({
            "name": clean_text(row.get("name")),
            "category": category,
            "category_path": [category] if category else [],
            "product_type": None,
            "item_kind": "товар",
            "unit": row.get("unit") or None,
            "pack_quantity": None,
            "pack_unit": None,
            "price": price,
            "price_date": None,
            "currency": "RUB" if price is not None else None,
            "manufacturer": manufacturer,
            "article": article,
            "description": None,  # реклама магазина — не переносим (владелец, 26.10)
            "characteristics": characteristics,
            "photos": photos,
            "links": links,
            "source_url": url,
            "source_id": None,
            "is_reusable": None,
            "is_active": None,
        })

    return {"source": "store_nomenclature", "items": items}
