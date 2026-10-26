"""Конвертер выгрузки vkusvill.ru → формат GALA (см. format.py).

Выгрузка встречается в ДВУХ формах в пределах проверенных файлов (владелец,
26.10) — различаем по наличию ключа "id" у элемента (плоский формат его не
содержит):

1) Плоский (150-формат, vkusvill_grocery_nomenclature.json):
   {name, category, price (число, 0 → null), unit, url, photo, description}
   → простое отображение: category как есть, category_path=[category],
     photos=[photo] если есть, source_url=url, links=[{"url","price"}] если
     url, product_type=null, characteristics=[].

2) Структурный (1000/massive-формат, vkusvill_grocery_nomenclature_1000.json):
   {id, name, slug, description, price:{current,...}, unit,
    weight:{value,unit}, rating, url, images:[{small,medium,large}],
    category:[{name,...}], properties:[{name,value}]}
   Проверено на реальном файле (1003 позиции, 26.10): category — список ОТ
   ЛИСТА К КОРНЮ (category[0] — самая конкретная подкатегория, например
   "Творог", последний элемент — корневая рубрика, например "Молочные
   продукты, яйцо" или даже 3-4 уровня вверх типа "Особое питание"). Поэтому:
     - category_path = список имён, развёрнутый в порядке "от родителя к
       листу" (reversed), как требует формат GALA;
     - product_type = последний элемент ЭТОГО перевёрнутого списка, то есть
       лист (самая конкретная подкатегория, category[0] до разворота);
     - верхнеуровневая category — КОНСТАНТА "Продукты питания" (вся выгрузка
       об одном товарном домене, растить дерево категорий в это поле не
       просят).
   price = price.current (0/отсутствует → null). photos = [img["large"] for
   img in images]. characteristics — из properties (name/value, "<br>" в
   value → "\n", см. HTML-переносы в составе/пищевой ценности), плюс, если
   задан weight.value — характеристика {"name":"Вес","value":str(value),
   "unit":weight.unit}. source_id = str(id). rating НЕ переносится в GALA.

Пустой список raw=[] (встречается в vkusvill_grocery_nomenclature_massive.json
на момент проверки) → {"source":"vkusvill","items":[]}, без ошибки — ждём
данных отдельной выгрузкой.

name/значения характеристик (properties, "Вес") чистятся через
catalog_gala.clean.clean_text (ПРАВИЛО №6) — единственная функция очистки
HTML-мусора (сущности типа &nbsp;, теги <br>) для ВСЕХ конвертеров; раньше
здесь была собственная _replace_br, которая заменяла только <br> и не трогала
HTML-сущности (владелец, 2026-10-26: «Творог "Пластовой" ..., 250&nbsp;г»).

description НЕ переносится (владелец, 2026-10-26): текст ВкусВилла в этом
поле — рекламное описание товара, не характеристика; техописание карточки
собирается только из characteristics (см.
services/product_tech_description.py::build_tech_description).
"""
from app.services.catalog_gala.clean import clean_text

_GROCERY_CATEGORY = "Продукты питания"


def _convert_flat_item(row: dict) -> dict:
    price = row.get("price") or None
    if price == 0:
        price = None
    category = row.get("category") or None
    url = row.get("url") or None
    photo = row.get("photo") or None

    return {
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
        "manufacturer": None,
        "article": None,
        "description": None,  # реклама, не характеристика (владелец, 26.10)
        "characteristics": [],
        "photos": [photo] if photo else [],
        "links": [{"url": url, "price": price}] if url else [],
        "source_url": url,
        "source_id": None,
        "is_reusable": None,
        "is_active": None,
    }


def _convert_structured_item(row: dict) -> dict:
    price_obj = row.get("price") or {}
    price = price_obj.get("current") if isinstance(price_obj, dict) else None
    if not price:
        price = None
    currency = price_obj.get("currency") if isinstance(price_obj, dict) else None

    raw_category = row.get("category") or []
    category_names_leaf_first = [c.get("name") for c in raw_category if isinstance(c, dict) and c.get("name")]
    category_path = list(reversed(category_names_leaf_first))
    product_type = category_path[-1] if category_path else None

    images = row.get("images") or []
    photos = [img.get("large") for img in images if isinstance(img, dict) and img.get("large")]

    characteristics = []
    for prop in (row.get("properties") or []):
        if not isinstance(prop, dict):
            continue
        name = clean_text(prop.get("name"))
        if not name:
            continue
        characteristics.append({"name": name, "value": clean_text(prop.get("value")), "unit": None})

    weight = row.get("weight") or {}
    if isinstance(weight, dict) and weight.get("value") is not None:
        characteristics.append({
            "name": "Вес",
            "value": str(weight.get("value")),
            "unit": clean_text(weight.get("unit")),
        })

    url = row.get("url") or None
    product_id = row.get("id")

    return {
        "name": clean_text(row.get("name")),
        "category": _GROCERY_CATEGORY,
        "category_path": category_path,
        "product_type": product_type,
        "item_kind": "товар",
        "unit": row.get("unit") or None,
        "pack_quantity": None,
        "pack_unit": None,
        "price": price,
        "price_date": None,
        "currency": currency,
        "manufacturer": None,
        "article": None,
        "description": None,  # реклама, не характеристика (владелец, 26.10)
        "characteristics": characteristics,
        "photos": photos,
        "links": [{"url": url, "price": price}] if url else [],
        "source_url": url,
        "source_id": str(product_id) if product_id is not None else None,
        "is_reusable": None,
        "is_active": None,
    }


def convert(raw: list, source_file: str) -> dict:
    items = []
    for row in raw or []:
        if isinstance(row, dict) and "id" in row:
            items.append(_convert_structured_item(row))
        else:
            items.append(_convert_flat_item(row))

    return {"source": "vkusvill", "items": items}
