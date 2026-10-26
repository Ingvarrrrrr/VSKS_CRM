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

Названия поставщиков в "Состав"/"Пищевая и энергетическая ценность в 100 г"
(владелец, 2026-10-26, Задача 2) — у части товаров значение собрано из
нескольких поставщиков построчно, у каждой строки свой текст с префиксом/
суффиксом вида "ООО «ИМЯ»:<текст>;" (организационная форма — ООО/ОАО/АО/
ЗАО/ПАО/ИП/КФХ/СПК, до или после названия, до первого ":" в строке), плюс
может быть отдельный хвост "Поставщики:ООО А;ООО Б;..." (в той же строке
после основного текста ЛИБО отдельной строкой). Обработка (_strip_suppliers,
на значении, уже прошедшем clean_text — <br> уже заменены на "\n"):
  1. В каждой строке ищем "Поставщики:<список через ';'>" (в любом месте
     строки, не только в начале) — список организаций вынимается, остаток
     строки до найденного текста — содержимое этой строки.
  2. Если оставшееся содержимое строки начинается с "<организация>:" (вся
     часть строки до первого ":" содержит слово из списка форм) — название
     организации вынимается, остаток после ":" — содержимое строки.
  3. Собранные названия организаций со всех строк — без дублей, по порядку
     первого упоминания.
  4. Содержимое строк (после вырезания организаций) — без дублей (если у
     разных поставщиков текст совпал буквально, оставляем один экземпляр);
     разные варианты — каждый с новой строки, без имени поставщика.
Названия организаций со всех характеристик товара (Состав + Пищевая
ценность) объединяются в ОДНУ характеристику "Поставщики" (через "; ",
in_description=False — это данные о логистике поставщика, не о товаре).
"""
import re

from app.services.catalog_gala.clean import clean_text
from app.services.catalog_gala.stores import seller_inn_for_url

_GROCERY_CATEGORY = "Продукты питания"

_ORG_FORMS_RE = r"(?:ООО|ОАО|АО|ЗАО|ПАО|ИП|КФХ|СПК)"
_SUPPLIERS_MARKER_RE = re.compile(r"Поставщики\s*:\s*(.+)$", re.IGNORECASE)
_ORG_PREFIX_RE = re.compile(r"^([^:]{1,100}):\s*(.*)$")
_ORG_TOKEN_RE = re.compile(r"\b" + _ORG_FORMS_RE + r"\b")


def _strip_suppliers(value):
    """Возвращает (очищенное_значение, [название_организации, ...]) —
    см. докстринг модуля. value уже прошло clean_text."""
    if not value:
        return value, []

    orgs = []
    contents = []
    for line in value.split("\n"):
        line = line.strip()
        if not line:
            continue

        m = _SUPPLIERS_MARKER_RE.search(line)
        if m:
            orgs.extend(o.strip() for o in m.group(1).split(";") if o.strip())
            line = line[: m.start()].rstrip(" ;").strip()

        if line:
            m2 = _ORG_PREFIX_RE.match(line)
            if m2 and _ORG_TOKEN_RE.search(m2.group(1)):
                orgs.append(m2.group(1).strip())
                line = m2.group(2).strip()

        # Разделитель между строками поставщика в исходнике — ";" перед
        # "<br>" (ставшим "\n" после clean_text) — хвостовой "." у нас не
        # мусор (конец предложения), а вот одинокая ";" — артефакт формата.
        line = line.rstrip(";").strip()

        if line and line not in contents:
            contents.append(line)

    # Дедуп организаций, порядок первого упоминания.
    seen = set()
    uniq_orgs = []
    for o in orgs:
        if o not in seen:
            seen.add(o)
            uniq_orgs.append(o)

    clean_value = "\n".join(contents) if contents else None
    return clean_value, uniq_orgs


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
        "seller_inn": seller_inn_for_url(url),
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
    supplier_orgs = []
    for prop in (row.get("properties") or []):
        if not isinstance(prop, dict):
            continue
        name = clean_text(prop.get("name"))
        if not name:
            continue
        value = clean_text(prop.get("value"))

        name_lower = name.lower()
        if name_lower == "состав" or name_lower.startswith("пищевая и энергетическая ценность"):
            value, orgs = _strip_suppliers(value)
            for o in orgs:
                if o not in supplier_orgs:
                    supplier_orgs.append(o)

        characteristics.append({"name": name, "value": value, "unit": None})

    if supplier_orgs:
        characteristics.append({
            "name": "Поставщики",
            "value": "; ".join(supplier_orgs),
            "unit": None,
            "in_description": False,
        })

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
        "seller_inn": seller_inn_for_url(url),
    }


def convert(raw: list, source_file: str) -> dict:
    items = []
    for row in raw or []:
        if isinstance(row, dict) and "id" in row:
            items.append(_convert_structured_item(row))
        else:
            items.append(_convert_flat_item(row))

    return {"source": "vkusvill", "items": items}
