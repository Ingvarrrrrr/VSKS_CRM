"""Конвертер выгрузки baucenter.ru → формат GALA (см. format.py).

Вход (raw) — список объектов вида:
  {id, name, brand, article, category, unit, price, url, photo, all_photos,
   description, specifications: {"<Имя> (<ед>)": "<значение>", ...}}

Проверено на реальном файле (baucenter_construction_all.json, 13045 позиций,
26.10): 298 различных значений category (лист строительных товаров), price
везде задана (0 не встречается, но правило «0 → null» — такое же, как у
остальных конвертеров, на случай будущих выгрузок), 28 названий встречаются
повторно в файле — у разных article (например «Линолеум Дельта Томас 3,5
м/2,5 мм» под article 101004840 и 101001481). Это НЕ дефект выгрузки: такие
повторы сольются в один товар каталога по правилу owner'а «одинаковое
название = тот же товар» (см. services/products_import_match.py), что и для
остальных источников. specifications — 523 разных ключа вида "<Имя> (<ед>)"
("Диаметр (мм)", "Вес брутто (кг)", "Расход в один слой до (м2/л)") —
разбираются той же функцией, что и у electro_mpo (services/catalog_gala/
spec_parse.py, ПРАВИЛО №6), включая нормализацию составных единиц.

Правила отображения полей:
  - id → source_id (str).
  - description НЕ переносится (владелец, 2026-10-26): текст Baucenter —
    рекламное описание, не характеристика; техописание карточки собирается
    только из characteristics.
  - name чистится через catalog_gala.clean.clean_text (ПРАВИЛО №6) — в
    описаниях встречаются числовые HTML-сущности вроде "&#40;"/"&#41;".
  - brand → manufacturer (пусто → None).
  - article → article (пусто → None).
  - category (298 листовых значений) → по аналогии с ВкусВиллом: верхний
    уровень category — КОНСТАНТА "Строительные и отделочные материалы" (вся
    выгрузка об одном товарном домене), конкретное значение из файла идёт в
    category_path=[значение] и product_type=значение (вид товара).
  - unit → unit как есть (пусто → None).
  - price: 0/пусто → None.
  - url → source_url и links=[{"url":url,"price":price}], если url есть.
  - all_photos → photos (если пуст — фолбэк на одиночное photo, если оно
    есть); все элементы чистятся через clean_text на случай HTML-мусора в
    ссылках (как и у прочих текстовых полей).
  - specifications → characteristics, по ключу:
      * "Страна производства"/"Страна производитель"/"Страна изготовитель"
        (дефис в ключе нормализуется в пробел перед сравнением — список
        имён ключа вынесен в app.services.catalog_gala.country_names,
        ПРАВИЛО №6, тот же модуль использует from_store_nomenclature.py;
        "страна изготовитель" добавлена 26.10.2026, находка владельца:
        country_origin='РФ' дефолт у baucenter_electro_lighting/
        baucenter_tools_hardware — перенос страны из файла появился позже
        загрузки) → ТАКЖЕ item["country_origin"] (новое опциональное поле
        GALA, см. format.py) — апстрим (products_import_apply.py/
        load_gala_catalog.py) заполняет Product.country_origin, если он
        пуст или равен дефолту "РФ"; при этом характеристику из
        characteristics НЕ убираем — владелец прямо попросил оставить её
        видимой в карточке тоже. "Производство"/"Производство изделия" —
        НЕ страна (в baucenter такие ключи не встречались при проверке
        26.10.2026 — specifications этой выгрузки используют только три
        варианта выше), country_names.COUNTRY_KEY_NAMES их не содержит.
      * "Марка" — если значение совпадает с brand (без учёта регистра/
        пробелов), в characteristics НЕ дублируется (manufacturer уже несёт
        этот факт); отличается от brand или brand пуст — остаётся обычной
        характеристикой.
      * "Вес брутто" — обычная характеристика, остаётся в описании (никакого
        in_description=False — это правило только у electro_mpo).
      * все остальные ключи — через spec_parse.split_key_unit, как есть.
  - item_kind = "товар" (только товары в этой выгрузке).
  - is_reusable/is_active не определены в исходнике → null.
"""
from app.services.catalog_gala.clean import clean_text
from app.services.catalog_gala.country_names import COUNTRY_KEY_NAMES, norm_country_key
from app.services.catalog_gala.spec_parse import split_key_unit
from app.services.catalog_gala.stores import seller_inn_for_url

# baucenter.ru — article_is_manufacturer=False (stores.py): "article" этой
# выгрузки — номер товара в КАТАЛОГЕ БАУЦЕНТРА (своя нумерация магазина, не
# производителя) — владелец, 27.10.2026. Эта выгрузка всегда Бауцентр, решение
# фиксировано здесь (как у electro_mpo, не через split_legacy_article).

_CONSTRUCTION_CATEGORY = "Строительные и отделочные материалы"


def _norm_eq(a, b) -> bool:
    return (a or "").strip().lower() == (b or "").strip().lower()


def _parse_specifications(specs: dict, brand) -> tuple:
    """Возвращает (characteristics, country_origin)."""
    characteristics = []
    country_origin = None

    for raw_key, raw_value in (specs or {}).items():
        key_lower = raw_key.strip().lower()
        value = clean_text(raw_value)

        if norm_country_key(key_lower) in COUNTRY_KEY_NAMES:
            country_origin = value
            characteristics.append({"name": clean_text(raw_key) or raw_key, "value": value, "unit": None})
            continue

        if key_lower == "марка" and _norm_eq(value, brand):
            continue  # уже в manufacturer — не дублируем

        name, unit = split_key_unit(raw_key)
        characteristics.append({"name": name, "value": value, "unit": unit})

    return characteristics, country_origin


def _convert_row(row: dict) -> dict:
    price = row.get("price") or None
    if price == 0:
        price = None

    category_leaf = clean_text(row.get("category")) or None
    category_path = [category_leaf] if category_leaf else []

    url = row.get("url") or None
    links = [{"url": url, "price": price}] if url else []

    all_photos = [clean_text(p) for p in (row.get("all_photos") or []) if p]
    if not all_photos:
        photo = row.get("photo") or None
        all_photos = [clean_text(photo)] if photo else []

    brand = row.get("brand") or None
    characteristics, country_origin = _parse_specifications(row.get("specifications") or {}, brand)

    product_id = row.get("id")

    return {
        "name": clean_text(row.get("name")),
        "category": _CONSTRUCTION_CATEGORY,
        "category_path": category_path,
        "product_type": category_leaf,
        "item_kind": "товар",
        "unit": row.get("unit") or None,
        "pack_quantity": None,
        "pack_unit": None,
        "price": price,
        "price_date": None,
        "currency": "RUB" if price is not None else None,
        "manufacturer": brand,
        "manufacturer_article": None,
        "store_article": row.get("article") or None,
        "description": None,  # реклама, не характеристика (владелец, 26.10)
        "characteristics": characteristics,
        "country_origin": country_origin,
        "photos": all_photos,
        "links": links,
        "source_url": url,
        "source_id": str(product_id) if product_id is not None else None,
        "is_reusable": None,
        "is_active": None,
        "seller_inn": seller_inn_for_url(url),
    }


def convert(raw: list, source_file: str) -> dict:
    items = [_convert_row(row) for row in (raw or [])]
    return {"source": "baucenter", "items": items}
